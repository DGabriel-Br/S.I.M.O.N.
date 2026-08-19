import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from simon.events import get_event
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.process_binding import ProcessRunRequest
from simon.process_execution import execute_next_process_run
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage


def _goal_and_plan(database_path: Path, *, capability: str = "process.run") -> tuple[Goal, str]:
    goal = Goal.create(
        title="Executar script",
        origin="USER",
        desired_state={"description": "O script foi executado e seu resultado foi observado."},
        success_criteria=({"description": "Existe evidência da execução."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script informado pelo usuário.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": capability,
                "verification": "A execução produziu resultado técnico observável.",
            },
        ),
    )
    return goal, plan.id


def _request(tmp_path: Path, *arguments: str, timeout_seconds: float = 5) -> ProcessRunRequest:
    return ProcessRunRequest(
        executable=sys.executable,
        arguments=arguments,
        working_directory=str(tmp_path),
        timeout_seconds=timeout_seconds,
    )


def test_process_run_executes_structured_request_and_preserves_raw_output(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    request = _request(
        tmp_path,
        "-c",
        "import sys; print('saida-ok'); print('aviso', file=sys.stderr)",
    )

    receipt = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=request,
        trace_id="trc_process_test",
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.action.kind == "process.run"
    assert receipt.action.plan_id == plan_id
    assert receipt.exit_code == 0
    assert receipt.stdout.strip() == "saida-ok"
    assert receipt.stderr.strip() == "aviso"
    assert receipt.action.reported_result is not None
    assert receipt.action.reported_result["execution_event_id"] == receipt.execution_event_id
    assert receipt.action.reported_result["exit_code"] == 0
    assert receipt.action.failure is None

    event = get_event(database_path, receipt.execution_event_id)
    assert event is not None
    assert event.kind == "process.execution.completed"
    assert event.source == "tool"
    assert event.trace_id == "trc_process_test"
    assert event.payload["stdout"].strip() == "saida-ok"  # type: ignore[union-attr]
    assert event.payload["stderr"].strip() == "aviso"  # type: ignore[union-attr]

    with sqlite3.connect(database_path) as connection:
        authorization = connection.execute(
            "SELECT source, payload_json FROM events WHERE id = ?",
            (receipt.authorization_event_id,),
        ).fetchone()

    assert authorization is not None
    assert authorization[0] == "user"
    assert receipt.action.input_data["authorization_event_id"] == receipt.authorization_event_id

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.next_step is None
    assert readiness.steps[0].blockers[0].kind == "VERIFICATION_PENDING"
    assert readiness.steps[0].blockers[0].detail == receipt.action.id


def test_executor_passes_exact_argv_without_shell(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    request = _request(tmp_path, "script.py", "--mode", "check")
    captured: dict[str, object] = {}

    def fake_run(args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")  # type: ignore[arg-type]

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "simon.process_execution.subprocess.run",
        fake_run,
    )

    execute_next_process_run(database_path, goal_id=goal.id, request=request)

    assert captured["args"] == request.argv()
    assert captured["shell"] is False
    assert captured["cwd"] == request.working_directory
    assert captured["timeout"] == request.timeout_seconds


def test_nonzero_exit_is_observed_completion_not_executor_failure(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)

    receipt = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=_request(tmp_path, "-c", "import sys; print('erro', file=sys.stderr); sys.exit(7)"),
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.exit_code == 7
    assert receipt.stderr.strip() == "erro"
    assert receipt.action.failure is None


def test_missing_executable_marks_action_as_failed(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    request = ProcessRunRequest(
        executable=str(tmp_path / "executavel-que-nao-existe"),
        working_directory=str(tmp_path),
        timeout_seconds=5,
    )

    receipt = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=request,
    )

    assert receipt.action.status == "FAILED"
    assert receipt.exit_code is None
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "process_start"

    event = get_event(database_path, receipt.execution_event_id)
    assert event is not None
    assert event.kind == "process.execution.failed"
    assert event.payload["failure_kind"] == "process_start"


def test_timeout_marks_action_as_failed(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)

    receipt = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=_request(
            tmp_path,
            "-c",
            "import time; print('inicio', flush=True); time.sleep(2)",
            timeout_seconds=0.1,
        ),
    )

    assert receipt.action.status == "FAILED"
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "process_timeout"


def test_process_run_requires_existing_working_directory(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    request = ProcessRunRequest(
        executable=sys.executable,
        arguments=("-c", "print('nunca executado')"),
        working_directory=str(tmp_path / "ausente"),
    )

    with pytest.raises(ValueError, match="diretório de trabalho não encontrado"):
        execute_next_process_run(database_path, goal_id=goal.id, request=request)


def test_process_run_refuses_to_bypass_next_ready_capability(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path, capability="user.ask")

    with pytest.raises(ValueError, match="não usa a capability process.run"):
        execute_next_process_run(
            database_path,
            goal_id=goal.id,
            request=_request(tmp_path, "-c", "print('nunca executado')"),
        )


def test_process_run_does_not_silently_repeat_unverified_attempt(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    request = _request(tmp_path, "-c", "print('uma vez')")

    execute_next_process_run(database_path, goal_id=goal.id, request=request)

    with pytest.raises(ValueError, match="não possui step READY"):
        execute_next_process_run(database_path, goal_id=goal.id, request=request)


def test_failed_process_can_be_retried_explicitly_and_then_verified(tmp_path: Path) -> None:
    from simon.process_execution import retry_process_run
    from simon.process_verification import verify_process_run_execution

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    missing = ProcessRunRequest(
        executable=str(tmp_path / "missing-executable"),
        working_directory=str(tmp_path),
        timeout_seconds=5,
    )
    failed = execute_next_process_run(database_path, goal_id=goal.id, request=missing)
    assert failed.action.status == "FAILED"

    blocked = evaluate_active_plan(database_path, goal_id=goal.id)
    assert blocked.next_step is None
    assert blocked.steps[0].blockers[0].kind == "PREVIOUS_ATTEMPT_REQUIRES_REVIEW"

    retry = retry_process_run(
        database_path,
        action_id=failed.action.id,
        request=_request(tmp_path, "-c", "print('recovered')"),
        trace_id="trc_process_retry",
    )

    assert retry.action.status == "COMPLETED"
    assert retry.retry_of_action_id == failed.action.id
    assert retry.stdout.strip() == "recovered"
    assert retry.action.input_data["retry_of_action_id"] == failed.action.id

    authorization = get_event(database_path, retry.authorization_event_id)
    assert authorization is not None
    assert authorization.kind == "action.retry.authorized"
    assert authorization.source == "user"
    assert authorization.payload["retry_of_action_id"] == failed.action.id
    assert authorization.payload["previous_status"] == "FAILED"

    verified = verify_process_run_execution(database_path, action_id=retry.action.id)
    assert verified.verification.status == "VERIFIED"
    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"


def test_interrupted_process_can_be_retried_after_restart_reconciliation(tmp_path: Path) -> None:
    from simon.actions import create_action, interrupt_running_actions, transition_action
    from simon.process_execution import retry_process_run

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="process.run",
        input_data={"verification": "A execução produziu resultado técnico observável."},
    )
    transition_action(database_path, action.id, "RUNNING")
    interrupted = interrupt_running_actions(database_path)
    assert interrupted[0].status == "INTERRUPTED"

    retry = retry_process_run(
        database_path,
        action_id=action.id,
        request=_request(tmp_path, "-c", "print('after-restart')"),
    )

    assert retry.action.status == "COMPLETED"
    assert retry.retry_of_action_id == action.id
    assert retry.stdout.strip() == "after-restart"


def test_process_retry_rejects_completed_attempt(tmp_path: Path) -> None:
    from simon.process_execution import retry_process_run

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    completed = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=_request(tmp_path, "-c", "print('ok')"),
    )

    with pytest.raises(ValueError, match="FAILED ou INTERRUPTED"):
        retry_process_run(
            database_path,
            action_id=completed.action.id,
            request=_request(tmp_path, "-c", "print('retry')"),
        )


def test_process_retry_rejects_stale_attempt_after_new_retry(tmp_path: Path) -> None:
    from simon.process_execution import retry_process_run

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    missing = ProcessRunRequest(
        executable=str(tmp_path / "missing-executable"),
        working_directory=str(tmp_path),
        timeout_seconds=5,
    )
    first = execute_next_process_run(database_path, goal_id=goal.id, request=missing)
    second = retry_process_run(
        database_path,
        action_id=first.action.id,
        request=missing,
    )
    assert second.action.status == "FAILED"

    with pytest.raises(ValueError, match="outros blockers|tentativa mais recente"):
        retry_process_run(
            database_path,
            action_id=first.action.id,
            request=_request(tmp_path, "-c", "print('late')"),
        )

    third = retry_process_run(
        database_path,
        action_id=second.action.id,
        request=_request(tmp_path, "-c", "print('latest')"),
    )
    assert third.action.status == "COMPLETED"


def test_process_retry_does_not_bypass_other_step_blockers(tmp_path: Path) -> None:
    from simon.actions import create_action, transition_action
    from simon.process_execution import retry_process_run

    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Executar com condição",
        origin="USER",
        desired_state={"description": "Executado"},
        success_criteria=({"description": "Execução observada"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar somente depois da condição externa.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": ["serviço externo disponível"],
                "capability": "process.run",
                "verification": "Execução observada.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
        input_data={"verification": "Execução observada."},
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "FAILED",
        failure={"kind": "process_start", "message": "falha"},
    )

    with pytest.raises(ValueError, match="não pode ignorar outros blockers"):
        retry_process_run(
            database_path,
            action_id=action.id,
            request=_request(tmp_path, "-c", "print('nope')"),
        )
