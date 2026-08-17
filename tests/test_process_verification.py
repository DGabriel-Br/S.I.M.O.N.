import json
import sqlite3
import sys
from pathlib import Path

import pytest

from simon.actions import create_action
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.process_binding import ProcessRunRequest
from simon.process_execution import execute_next_process_run
from simon.process_verification import VERIFICATION_TYPE, verify_process_run_execution
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.verification import list_verification_results


def _goal_and_plan(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Executar e observar script",
        origin="USER",
        desired_state={"description": "execução observada"},
        success_criteria=({"description": "resultado técnico registrado"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução produziu resultado técnico observável.",
            },
            {
                "id": "step_02",
                "description": "Analisar o resultado.",
                "kind": "EPISTEMIC",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "unknown",
                "verification": "Existe uma análise do resultado.",
            },
        ),
    )
    return goal, plan.id


def _execute(database_path: Path, tmp_path: Path, *, exit_code: int = 0):
    goal, plan_id = _goal_and_plan(database_path)
    receipt = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=ProcessRunRequest(
            executable=sys.executable,
            arguments=(
                "-c",
                (
                    "import sys; print('saida'); print('erro', file=sys.stderr); "
                    f"sys.exit({exit_code})"
                ),
            ),
            working_directory=str(tmp_path),
            timeout_seconds=5,
        ),
    )
    return goal, plan_id, receipt


def test_process_verification_uses_completed_execution_event_as_objective_evidence(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _, execution = _execute(database_path, tmp_path)

    receipt = verify_process_run_execution(database_path, action_id=execution.action.id)

    assert receipt.created is True
    assert receipt.verification.status == "VERIFIED"
    assert receipt.verification.strength == 3
    assert receipt.verification.subject_id == execution.action.id
    assert receipt.verification.evidence_event_ids == (execution.execution_event_id,)
    assert receipt.verification.criteria[0]["type"] == VERIFICATION_TYPE
    assert receipt.verification.observed["verification_type"] == VERIFICATION_TYPE
    assert receipt.verification.observed["exit_code"] == 0
    assert receipt.verification.observed["stdout"].strip() == "saida"  # type: ignore[union-attr]
    assert receipt.verification.observed["stderr"].strip() == "erro"  # type: ignore[union-attr]
    assert receipt.verification.observed["semantic_effect_assessed"] is False
    assert (
        receipt.verification.observed["plan_verification_intent"]
        == "A execução produziu resultado técnico observável."
    )

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"
    assert readiness.steps[0].related_action_id == execution.action.id
    assert readiness.steps[1].state == "BLOCKED"


def test_nonzero_exit_is_still_verified_as_observed_execution(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _, _, execution = _execute(database_path, tmp_path, exit_code=7)

    receipt = verify_process_run_execution(database_path, action_id=execution.action.id)

    assert receipt.verification.status == "VERIFIED"
    assert receipt.verification.observed["exit_code"] == 7
    assert receipt.verification.observed["semantic_effect_assessed"] is False


def test_process_verification_is_idempotent_for_same_execution_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _, _, execution = _execute(database_path, tmp_path)

    first = verify_process_run_execution(database_path, action_id=execution.action.id)
    second = verify_process_run_execution(database_path, action_id=execution.action.id)

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=execution.action.id,
    ) == (first.verification,)


def test_process_verification_rejects_failed_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_plan(database_path)
    execution = execute_next_process_run(
        database_path,
        goal_id=goal.id,
        request=ProcessRunRequest(
            executable=str(tmp_path / "missing-executable"),
            working_directory=str(tmp_path),
            timeout_seconds=5,
        ),
    )

    with pytest.raises(ValueError, match="está FAILED"):
        verify_process_run_execution(database_path, action_id=execution.action.id)


def test_process_verification_rejects_non_process_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="user.ask",
        input_data={"prompt": "x", "verification": "x"},
    )

    with pytest.raises(ValueError, match="não representa process.run"):
        verify_process_run_execution(database_path, action_id=action.id)


def test_process_verification_rejects_tampered_execution_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _, _, execution = _execute(database_path, tmp_path)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE id = ?",
            (execution.execution_event_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[0]))
        payload["action_id"] = "act_outra"
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE id = ?",
            (json.dumps(payload), execution.execution_event_id),
        )

    with pytest.raises(ValueError, match="não pertence à Action"):
        verify_process_run_execution(database_path, action_id=execution.action.id)


def test_process_verification_rejects_stale_step_attempt(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, execution = _execute(database_path, tmp_path)
    create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="process.run",
        input_data={"verification": "nova tentativa"},
    )

    with pytest.raises(ValueError, match="tentativa mais recente"):
        verify_process_run_execution(database_path, action_id=execution.action.id)
