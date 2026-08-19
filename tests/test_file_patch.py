from pathlib import Path

import pytest
from pydantic import ValidationError

from simon.actions import create_action, list_actions_for_plan, transition_action
from simon.events import Event, append_event, get_event
from simon.file_patch import (
    FilePatchRequest,
    bind_file_patch_step,
    execute_next_file_patch,
    retry_file_patch,
)
from simon.file_patch_verification import verify_file_patch_state
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def _goal_and_change_plan(
    database_path: Path,
    *,
    depends_on: list[str] | None = None,
) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Corrigir arquivo",
        origin="USER",
        desired_state={"description": "O arquivo contém a correção localizada."},
        success_criteria=({"description": "A alteração foi aplicada e verificada."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Realizar a mudança: corrigir variável no script",
                "kind": "WORLD",
                "depends_on": depends_on or [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada da variável no script",
                "verification": "Arquivo modificado com a correção aplicada e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )
    return goal, plan.id


def _request(
    workspace: Path,
    *,
    expected: str = "valor = 1",
    replacement: str = "valor = 2",
) -> FilePatchRequest:
    return FilePatchRequest(
        workspace=str(workspace),
        relative_path="script.py",
        expected_text=expected,
        replacement_text=replacement,
    )


def test_file_patch_request_requires_relative_scoped_path() -> None:
    with pytest.raises(ValidationError, match="relative_path precisa permanecer relativo"):
        FilePatchRequest(
            workspace="C:/projeto",
            relative_path="C:/outro/script.py",
            expected_text="x = 1",
            replacement_text="x = 2",
        )

    with pytest.raises(ValidationError, match="não pode sair do workspace"):
        FilePatchRequest(
            workspace="C:/projeto",
            relative_path="../script.py",
            expected_text="x = 1",
            replacement_text="x = 2",
        )

    with pytest.raises(ValidationError, match="mudança efetiva"):
        FilePatchRequest(
            workspace="C:/projeto",
            relative_path="script.py",
            expected_text="x = 1",
            replacement_text="x = 1",
        )


def test_binding_accepts_only_typed_simon_change_unknown(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_change_plan(database_path)
    readiness = evaluate_active_plan(database_path, goal_id=goal.id)

    binding = bind_file_patch_step(
        readiness.plan,
        step_id="step_01",
        request=_request(tmp_path),
    )

    assert binding.goal_id == goal.id
    assert binding.step_id == "step_01"
    assert binding.capability_detail == "Correção localizada da variável no script"
    assert binding.verification == "Arquivo modificado com a correção aplicada e salvo."


def test_file_patch_applies_exact_localized_replacement_and_preserves_other_bytes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_bytes(b"cabecalho\r\nvalor = 1\r\nrodape\r\n")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)

    receipt = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
        trace_id="trc_file_patch_test",
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.action.kind == "file.patch"
    assert receipt.action.plan_id == plan_id
    assert receipt.before_sha256 is not None
    assert receipt.after_sha256 is not None
    assert receipt.before_sha256 != receipt.after_sha256
    assert target.read_bytes() == b"cabecalho\r\nvalor = 2\r\nrodape\r\n"
    assert receipt.action.reported_result is not None
    assert receipt.action.reported_result["modification_event_id"] == receipt.modification_event_id

    event = get_event(database_path, receipt.modification_event_id)
    assert event is not None
    assert event.kind == "file.patch.completed"
    assert event.source == "tool"
    assert event.trace_id == "trc_file_patch_test"
    assert event.payload["before_sha256"] == receipt.before_sha256
    assert event.payload["after_sha256"] == receipt.after_sha256

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.next_step is None
    assert readiness.steps[0].blockers[0].kind == "VERIFICATION_PENDING"


def test_file_patch_fails_without_writing_when_expected_text_is_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    original = b"valor = 3\n"
    target.write_bytes(original)

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)

    receipt = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )

    assert receipt.action.status == "FAILED"
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "expected_text_not_unique"
    assert target.read_bytes() == original
    actions = list_actions_for_plan(database_path, plan_id)
    assert len(actions) == 1


def test_file_patch_fails_without_writing_when_expected_text_is_ambiguous(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    original = b"valor = 1\nvalor = 1\n"
    target.write_bytes(original)

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_change_plan(database_path)

    receipt = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )

    assert receipt.action.status == "FAILED"
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "expected_text_not_unique"
    assert target.read_bytes() == original


def test_file_patch_does_not_bypass_other_blockers(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "script.py").write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Mudança bloqueada",
        origin="USER",
        desired_state={"description": "mudança aplicada"},
        success_criteria=({"description": "mudança verificada"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Realizar a mudança: alterar script",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": ["A revisão externa foi aprovada."],
                "capability": "unknown",
                "capability_detail": "Alteração do script",
                "verification": "Arquivo alterado.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )

    with pytest.raises(ValueError, match="não possui step CHANGE/unknown elegível"):
        execute_next_file_patch(
            database_path,
            goal_id=goal.id,
            request=_request(workspace),
        )

    assert target_text(workspace / "script.py") == "valor = 1\n"


def test_file_patch_refuses_generic_unknown_step(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "script.py").write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Coletar dado",
        origin="USER",
        desired_state={"description": "dado disponível"},
        success_criteria=({"description": "dado coletado"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Obter informação local",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Leitura de informação local",
                "verification": "Informação obtida.",
                "intent_role": "COLLECT",
                "intent_actor": "SIMON",
            },
        ),
    )

    with pytest.raises(ValueError, match="não possui step CHANGE/unknown elegível"):
        execute_next_file_patch(
            database_path,
            goal_id=goal.id,
            request=_request(workspace),
        )


def test_failed_file_patch_can_be_retried_with_corrected_request_and_verified(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 3\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)
    failed = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )
    assert failed.action.status == "FAILED"

    blocked = evaluate_active_plan(database_path, goal_id=goal.id)
    assert tuple(blocker.kind for blocker in blocked.steps[0].blockers) == (
        "PREVIOUS_ATTEMPT_REQUIRES_REVIEW",
        "CAPABILITY_UNAVAILABLE",
    )

    retried = retry_file_patch(
        database_path,
        action_id=failed.action.id,
        request=_request(workspace, expected="valor = 3", replacement="valor = 2"),
        trace_id="trc_file_retry",
    )

    assert retried.action.status == "COMPLETED"
    assert retried.retry_of_action_id == failed.action.id
    assert retried.action.input_data["retry_of_action_id"] == failed.action.id
    assert target.read_text(encoding="utf-8") == "valor = 2\n"

    authorization = get_event(database_path, retried.authorization_event_id)
    assert authorization is not None
    assert authorization.kind == "action.retry.authorized"
    assert authorization.source == "user"
    assert authorization.payload["capability"] == "file.patch"
    assert authorization.payload["retry_of_action_id"] == failed.action.id
    assert authorization.payload["previous_status"] == "FAILED"

    modification = get_event(database_path, retried.modification_event_id)
    assert modification is not None
    assert modification.payload["retry_of_action_id"] == failed.action.id

    actions = list_actions_for_plan(database_path, plan_id)
    assert [action.status for action in actions] == ["FAILED", "COMPLETED"]

    verified = verify_file_patch_state(database_path, action_id=retried.action.id)
    assert verified.verification.status == "VERIFIED"
    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"


def test_interrupted_file_patch_can_be_retried(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)
    interrupted = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="file.patch",
        input_data={"bound_from_capability": "unknown"},
    )
    transition_action(database_path, interrupted.id, "RUNNING")
    transition_action(
        database_path,
        interrupted.id,
        "INTERRUPTED",
        failure={"kind": "runtime_restart", "message": "runtime reiniciado"},
    )

    retried = retry_file_patch(
        database_path,
        action_id=interrupted.id,
        request=_request(workspace),
    )

    assert retried.action.status == "COMPLETED"
    assert retried.retry_of_action_id == interrupted.id
    assert target.read_text(encoding="utf-8") == "valor = 2\n"


def test_file_patch_retry_rejects_completed_attempt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "script.py").write_text("valor = 1\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_change_plan(database_path)
    completed = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )

    with pytest.raises(ValueError, match="FAILED ou INTERRUPTED"):
        retry_file_patch(
            database_path,
            action_id=completed.action.id,
            request=_request(workspace, expected="valor = 2", replacement="valor = 3"),
        )


def test_file_patch_retry_rejects_attempt_that_is_no_longer_latest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "script.py").write_text("valor = 3\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_change_plan(database_path)
    first = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )
    second = retry_file_patch(
        database_path,
        action_id=first.action.id,
        request=_request(workspace),
    )
    assert second.action.status == "FAILED"

    with pytest.raises(ValueError, match="outros blockers|tentativa mais recente"):
        retry_file_patch(
            database_path,
            action_id=first.action.id,
            request=_request(workspace),
        )


def test_file_patch_retry_refuses_to_bypass_dependency_that_lost_verification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "script.py").write_text("valor = 3\n", encoding="utf-8")

    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Corrigir após evidência",
        origin="USER",
        desired_state={"description": "arquivo corrigido"},
        success_criteria=({"description": "alteração verificada"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Observar estado anterior.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "Estado observado.",
            },
            {
                "id": "step_02",
                "description": "Realizar a mudança: corrigir arquivo",
                "kind": "WORLD",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada",
                "verification": "Arquivo modificado.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )
    prior = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    transition_action(database_path, prior.id, "RUNNING")
    transition_action(database_path, prior.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(
        kind="test.prior_state.observed",
        source="tool",
        payload={"action_id": prior.id},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    verified = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=prior.id,
        criteria=({"description": "Estado observado."},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"state": "present"},
        strength=3,
    )

    failed = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=_request(workspace),
    )
    assert failed.action.status == "FAILED"

    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=prior.id,
        criteria=verified.criteria,
        status="FAILED",
        evidence_event_ids=(evidence.id,),
        observed={"state": "invalidated"},
        strength=4,
    )

    with pytest.raises(ValueError, match="não pode ignorar outros blockers"):
        retry_file_patch(
            database_path,
            action_id=failed.action.id,
            request=_request(workspace, expected="valor = 3", replacement="valor = 2"),
        )


def target_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
