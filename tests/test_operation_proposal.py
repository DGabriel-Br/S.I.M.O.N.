from __future__ import annotations

import sys
from pathlib import Path

from simon.actions import list_actions_for_plan
from simon.cli import main
from simon.events import get_event
from simon.executive import decide_next
from simon.file_patch import FilePatchRequest
from simon.goals import Goal, insert_goal
from simon.operation_proposal import (
    find_current_file_patch_proposal,
    find_current_process_run_proposal,
    propose_file_patch,
    propose_process_run,
)
from simon.plans import create_plan
from simon.process_binding import ProcessRunRequest
from simon.storage import initialize_storage
from simon.user_turn import handle_user_turn


def _goal_and_plan(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Executar validação",
        origin="USER",
        desired_state={"description": "A validação foi executada."},
        success_criteria=({"description": "Existe evidência da execução."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar comando de validação.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução foi observada.",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )
    return goal, plan.id


def _request(tmp_path: Path, marker: str) -> ProcessRunRequest:
    return ProcessRunRequest(
        executable=sys.executable,
        arguments=("-c", f"print({marker!r})"),
        working_directory=str(tmp_path),
        timeout_seconds=5,
    )


def test_process_proposal_persists_exact_request_without_executing(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    request = _request(tmp_path, "proposal-only")

    proposal = propose_process_run(database_path, goal_id=goal.id, request=request)

    assert proposal.goal_id == goal.id
    assert proposal.plan_id == plan_id
    assert proposal.step_id == "step_01"
    assert proposal.request == request
    assert list_actions_for_plan(database_path, plan_id) == ()

    event = get_event(database_path, proposal.event.id)
    assert event is not None
    assert event.kind == "executive.operation.proposed"
    assert event.source == "system"
    assert event.payload["proposal_type"] == "process.run"
    assert event.payload["reason"]
    assert event.payload["verification"] == "A execução foi observada."
    assert event.payload["request"] == request.model_dump(mode="json")
    assert event.payload["argv"] == list(request.argv())

    decision = decide_next(database_path, goal_id=goal.id)
    current = find_current_process_run_proposal(database_path, decision)
    assert current is not None
    assert current.event.id == proposal.event.id


def test_affirmative_turn_without_concrete_proposal_still_authorizes_nothing(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "operation_proposal_required"
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_affirmative_turn_executes_only_current_process_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    request = _request(tmp_path, "authorized-proposal")
    proposal = propose_process_run(database_path, goal_id=goal.id, request=request)

    receipt = handle_user_turn(database_path, "pode executar", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.intent == "AUTHORIZE"
    assert receipt.effect_type == "process.run"
    assert receipt.routing_event.payload["authority_scope"] == "CURRENT_OPERATION_PROPOSAL_ONLY"
    assert receipt.routing_event.payload["proposal_event_id"] == proposal.event.id

    actions = list_actions_for_plan(database_path, plan_id)
    assert len(actions) == 1
    action = actions[0]
    assert action.id == receipt.effect_id
    assert action.kind == "process.run"
    assert action.input_data["request"] == request.model_dump(mode="json")
    authorization_event_id = action.input_data["authorization_event_id"]
    assert isinstance(authorization_event_id, str)
    authorization = get_event(database_path, authorization_event_id)
    assert authorization is not None
    assert authorization.kind == "process.run.authorized"
    assert authorization.source == "user"
    assert authorization.trace_id == receipt.turn_event.id

    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "MODEL_REQUIRED"
    assert receipt.executive_receipt.final_decision.operation == "goal.assess"


def test_latest_process_proposal_supersedes_older_request(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    first = propose_process_run(
        database_path,
        goal_id=goal.id,
        request=_request(tmp_path, "first"),
    )
    second_request = _request(tmp_path, "second")
    second = propose_process_run(database_path, goal_id=goal.id, request=second_request)

    assert second.event.payload["supersedes_proposal_event_id"] == first.event.id

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.routing_event.payload["proposal_event_id"] == second.event.id
    action = list_actions_for_plan(database_path, plan_id)[0]
    assert action.input_data["request"] == second_request.model_dump(mode="json")


def test_non_explicit_text_does_not_accept_current_process_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_plan(database_path)
    propose_process_run(database_path, goal_id=goal.id, request=_request(tmp_path, "no"))

    receipt = handle_user_turn(database_path, "ok", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == (
        "explicit_operation_authorization_required"
    )
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_process_propose_cli_presents_proposal_without_execution(
    tmp_path: Path,
    capsys: object,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, plan_id = _goal_and_plan(database_path)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "process-propose",
            goal.id,
            "--cwd",
            str(tmp_path),
            sys.executable,
            "-c",
            "print('cli-proposal')",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Proposta operacional:" in output
    assert "Tipo: process.run" in output
    assert "Execução realizada: não" in output
    assert "Autorização registrada: não" in output
    assert "pode executar" in output
    assert list_actions_for_plan(database_path, plan_id) == ()


def _goal_and_change_plan(database_path: Path) -> tuple[Goal, str]:
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
    return goal, plan.id


def _patch_request(
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


def test_file_patch_proposal_persists_exact_request_without_modifying_file(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)
    request = _patch_request(workspace)

    proposal = propose_file_patch(database_path, goal_id=goal.id, request=request)

    assert proposal.goal_id == goal.id
    assert proposal.plan_id == plan_id
    assert proposal.step_id == "step_01"
    assert proposal.capability_detail == "Correção localizada da variável no script"
    assert proposal.request == request
    assert target.read_text(encoding="utf-8") == "valor = 1\n"
    assert list_actions_for_plan(database_path, plan_id) == ()

    event = get_event(database_path, proposal.event.id)
    assert event is not None
    assert event.kind == "executive.operation.proposed"
    assert event.source == "system"
    assert event.payload["proposal_type"] == "file.patch"
    assert event.payload["operation"] == "plan.patch"
    assert event.payload["capability"] == "file.patch"
    assert event.payload["request"] == request.model_dump(mode="json")

    decision = decide_next(database_path, goal_id=goal.id)
    current = find_current_file_patch_proposal(database_path, decision)
    assert current is not None
    assert current.event.id == proposal.event.id


def test_affirmative_turn_applies_only_current_file_patch_proposal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)
    proposal = propose_file_patch(
        database_path,
        goal_id=goal.id,
        request=_patch_request(workspace),
    )

    receipt = handle_user_turn(database_path, "pode aplicar", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.intent == "AUTHORIZE"
    assert receipt.effect_type == "file.patch"
    assert receipt.routing_event.payload["authority_scope"] == "CURRENT_OPERATION_PROPOSAL_ONLY"
    assert receipt.routing_event.payload["proposal_event_id"] == proposal.event.id
    assert target.read_text(encoding="utf-8") == "valor = 2\n"

    actions = list_actions_for_plan(database_path, plan_id)
    assert len(actions) == 1
    action = actions[0]
    assert action.id == receipt.effect_id
    assert action.kind == "file.patch"
    authorization_event_id = action.input_data["authorization_event_id"]
    assert isinstance(authorization_event_id, str)
    authorization = get_event(database_path, authorization_event_id)
    assert authorization is not None
    assert authorization.kind == "file.patch.authorized"
    assert authorization.source == "user"
    assert authorization.trace_id == receipt.turn_event.id

    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "MODEL_REQUIRED"
    assert receipt.executive_receipt.final_decision.operation == "goal.assess"


def test_latest_file_patch_proposal_supersedes_older_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _goal_and_change_plan(database_path)
    first = propose_file_patch(
        database_path,
        goal_id=goal.id,
        request=_patch_request(workspace, replacement="valor = 2"),
    )
    second = propose_file_patch(
        database_path,
        goal_id=goal.id,
        request=_patch_request(workspace, replacement="valor = 3"),
    )

    assert second.event.payload["supersedes_proposal_event_id"] == first.event.id

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.routing_event.payload["proposal_event_id"] == second.event.id
    assert target.read_text(encoding="utf-8") == "valor = 3\n"


def test_file_propose_cli_presents_patch_without_modification(
    tmp_path: Path,
    capsys: object,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, plan_id = _goal_and_change_plan(database_path)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "file-propose",
            goal.id,
            "--workspace",
            str(workspace),
            "--file",
            "script.py",
            "--old",
            "valor = 1",
            "--new",
            "valor = 2",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Proposta operacional:" in output
    assert "Tipo: file.patch" in output
    assert "Arquivo: script.py" in output
    assert "valor = 1" in output
    assert "valor = 2" in output
    assert "Modificação realizada: não" in output
    assert "Autorização registrada: não" in output
    assert "pode aplicar" in output
    assert target.read_text(encoding="utf-8") == "valor = 1\n"
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_affirmative_turn_without_file_patch_proposal_modifies_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "operation_proposal_required"
    assert target.read_text(encoding="utf-8") == "valor = 1\n"
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_non_explicit_text_does_not_accept_current_file_patch_proposal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _goal_and_change_plan(database_path)
    propose_file_patch(
        database_path,
        goal_id=goal.id,
        request=_patch_request(workspace),
    )

    receipt = handle_user_turn(database_path, "ok", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == (
        "explicit_operation_authorization_required"
    )
    assert target.read_text(encoding="utf-8") == "valor = 1\n"
    assert list_actions_for_plan(database_path, plan_id) == ()
