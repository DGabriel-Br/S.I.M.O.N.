from __future__ import annotations

from pathlib import Path

import pytest

from simon.actions import create_action, list_actions_for_plan, transition_action
from simon.cli import main
from simon.goals import Goal, insert_goal
from simon.operation_materialization import (
    OperationMaterializationInputError,
    parse_process_command_turn,
)
from simon.operation_proposal import (
    find_current_process_retry_proposal,
    find_current_process_run_proposal,
)
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.user_turn import handle_user_turn


def _goal(database_path: Path, title: str = "Executar validação") -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"description": "A validação foi executada."},
        success_criteria=({"description": "A execução foi observada."},),
    )
    insert_goal(database_path, goal)
    return goal


def _process_plan(database_path: Path) -> tuple[Goal, str]:
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar a validação local.",
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


def test_parser_materializes_simple_foreground_process_command(tmp_path: Path) -> None:
    materialization = parse_process_command_turn(
        "Rode uv run pytest neste projeto.",
        working_directory=tmp_path,
    )

    assert materialization is not None
    assert materialization.command_text == "uv run pytest"
    assert materialization.request.executable == "uv"
    assert materialization.request.arguments == ("run", "pytest")
    assert materialization.request.working_directory == str(tmp_path.resolve())
    assert materialization.request.timeout_seconds == 120.0


def test_parser_rejects_shell_or_quoted_syntax_in_conversational_cut(tmp_path: Path) -> None:
    with pytest.raises(OperationMaterializationInputError) as shell_error:
        parse_process_command_turn(
            "Rode uv run pytest && echo ok neste projeto",
            working_directory=tmp_path,
        )
    assert shell_error.value.reason_code == "unsupported_process_command_syntax"

    with pytest.raises(OperationMaterializationInputError) as quoted_error:
        parse_process_command_turn(
            'Execute python -c "print(1)" neste projeto',
            working_directory=tmp_path,
        )
    assert quoted_error.value.reason_code == "unsupported_process_command_syntax"


def test_user_turn_materializes_process_run_without_authorizing_it(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _process_plan(database_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    receipt = handle_user_turn(
        database_path,
        "Rode uv run pytest neste projeto",
        goal_id=goal.id,
        working_directory=workspace,
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "MATERIALIZE"
    assert receipt.effect_type == "operation.proposal"
    assert receipt.effect_id is not None
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "STOPPED"
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert list_actions_for_plan(database_path, plan_id) == ()

    proposal = find_current_process_run_proposal(
        database_path,
        receipt.executive_receipt.final_decision,
    )
    assert proposal is not None
    assert proposal.event.id == receipt.effect_id
    assert proposal.event.trace_id == receipt.turn_event.id
    assert proposal.request.argv() == ("uv", "run", "pytest")
    assert proposal.request.working_directory == str(workspace.resolve())
    assert receipt.routing_event.payload["authority_scope"] == (
        "CURRENT_OPERATION_GATE_MATERIALIZATION_ONLY"
    )
    assert receipt.turn_event.payload["foreground_working_directory"] == str(workspace.resolve())


def test_user_turn_materializes_process_retry_for_current_failed_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _process_plan(database_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    failed = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="process.run",
        input_data={},
    )
    transition_action(database_path, failed.id, "RUNNING")
    transition_action(
        database_path,
        failed.id,
        "FAILED",
        failure={"kind": "start_failed", "message": "falha observada"},
    )

    receipt = handle_user_turn(
        database_path,
        "Execute uv run pytest neste projeto",
        goal_id=goal.id,
        working_directory=workspace,
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "MATERIALIZE"
    assert receipt.executive_receipt is not None
    proposal = find_current_process_retry_proposal(
        database_path,
        receipt.executive_receipt.final_decision,
    )
    assert proposal is not None
    assert proposal.retry_of_action_id == failed.id
    assert proposal.request.argv() == ("uv", "run", "pytest")
    actions = list_actions_for_plan(database_path, plan_id)
    assert [action.id for action in actions] == [failed.id]


def test_materialization_turn_does_not_double_as_authorization(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _process_plan(database_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    receipt = handle_user_turn(
        database_path,
        "Rode uv run pytest neste projeto e pode executar",
        goal_id=goal.id,
        working_directory=workspace,
    )

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == (
        "explicit_operation_authorization_required"
    )
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_user_turn_cli_materializes_and_immediately_presents_concrete_proposal(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, plan_id = _process_plan(database_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "--goal-id",
            goal.id,
            "Rode",
            "uv",
            "run",
            "pytest",
            "neste",
            "projeto",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "User turn: ROUTED" in output
    assert "Intent: MATERIALIZE" in output
    assert "Efeito do gate: operation.proposal" in output
    assert "Estado do gate: READY_FOR_AUTHORIZATION" in output
    assert "Executável: uv" in output
    assert "argv: uv run pytest" in output
    assert f"Diretório: {workspace.resolve()}" in output
    assert list_actions_for_plan(database_path, plan_id) == ()
