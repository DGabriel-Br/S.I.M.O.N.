import json
import sqlite3
from pathlib import Path

import pytest

from simon.actions import create_action
from simon.file_patch import FilePatchRequest, execute_next_file_patch
from simon.file_patch_verification import verify_file_patch_state
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage


def _execute_patch(database_path: Path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")

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
                "description": "Corrigir variável no script",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada da variável no script",
                "verification": "Arquivo modificado com a correção aplicada e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )
    execution = execute_next_file_patch(
        database_path,
        goal_id=goal.id,
        request=FilePatchRequest(
            workspace=str(workspace),
            relative_path="script.py",
            expected_text="valor = 1",
            replacement_text="valor = 2",
        ),
    )
    assert execution.action.status == "COMPLETED"
    return goal, plan, execution, target


def test_file_patch_verification_confirms_current_hash_without_semantic_claim(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _plan, execution, target = _execute_patch(database_path, tmp_path)

    receipt = verify_file_patch_state(database_path, action_id=execution.action.id)

    assert receipt.created is True
    assert receipt.verification.status == "VERIFIED"
    assert receipt.verification.strength == 4
    assert receipt.verification.evidence_event_ids == (execution.modification_event_id,)
    assert receipt.verification.observed["verification_type"] == "file.patch.current_state"
    assert receipt.verification.observed["current_state"] == "MATCHED"
    assert receipt.verification.observed["current_sha256"] == execution.after_sha256
    assert receipt.verification.observed["expected_after_sha256"] == execution.after_sha256
    assert receipt.verification.observed["semantic_effect_assessed"] is False
    assert target.read_text(encoding="utf-8") == "valor = 2\n"

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"


def test_file_patch_verification_is_idempotent_for_same_observed_state(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _goal, _plan, execution, _target = _execute_patch(database_path, tmp_path)

    first = verify_file_patch_state(database_path, action_id=execution.action.id)
    second = verify_file_patch_state(database_path, action_id=execution.action.id)

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id


def test_file_patch_verification_records_failed_when_file_changed_after_action(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _plan, execution, target = _execute_patch(database_path, tmp_path)
    target.write_text("valor = 3\n", encoding="utf-8")

    receipt = verify_file_patch_state(database_path, action_id=execution.action.id)

    assert receipt.verification.status == "FAILED"
    assert receipt.verification.observed["current_state"] == "HASH_MISMATCH"
    assert receipt.verification.observed["current_sha256"] != execution.after_sha256

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "BLOCKED"
    assert readiness.steps[0].blockers[0].kind == "VERIFICATION_FAILED"


def test_latest_file_verification_supersedes_older_result_for_readiness(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _plan, execution, target = _execute_patch(database_path, tmp_path)

    verified = verify_file_patch_state(database_path, action_id=execution.action.id)
    assert verified.verification.status == "VERIFIED"

    target.write_text("valor = 9\n", encoding="utf-8")
    failed = verify_file_patch_state(database_path, action_id=execution.action.id)
    assert failed.verification.status == "FAILED"
    assert failed.verification.id != verified.verification.id

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "BLOCKED"
    assert readiness.steps[0].blockers[0].kind == "VERIFICATION_FAILED"

    target.write_text("valor = 2\n", encoding="utf-8")
    restored = verify_file_patch_state(database_path, action_id=execution.action.id)
    assert restored.verification.status == "VERIFIED"
    assert restored.verification.id != verified.verification.id

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"


def test_file_patch_verification_records_failed_when_target_disappeared(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _goal, _plan, execution, target = _execute_patch(database_path, tmp_path)
    target.unlink()

    receipt = verify_file_patch_state(database_path, action_id=execution.action.id)

    assert receipt.verification.status == "FAILED"
    assert receipt.verification.observed["current_state"] == "TARGET_UNAVAILABLE"
    assert receipt.verification.observed["current_sha256"] is None


def test_file_patch_verification_rejects_tampered_modification_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _goal, _plan, execution, _target = _execute_patch(database_path, tmp_path)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE id = ?",
            (execution.modification_event_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[0]))
        payload["after_sha256"] = "0" * 64
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, separators=(",", ":")), execution.modification_event_id),
        )

    with pytest.raises(ValueError, match="divergem sobre after_sha256"):
        verify_file_patch_state(database_path, action_id=execution.action.id)


def test_file_patch_verification_rejects_non_file_patch_and_stale_attempt(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan, execution, _target = _execute_patch(database_path, tmp_path)

    other = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    with pytest.raises(ValueError, match="não representa file.patch"):
        verify_file_patch_state(database_path, action_id=other.id)

    with pytest.raises(ValueError, match="tentativa mais recente"):
        verify_file_patch_state(database_path, action_id=execution.action.id)
