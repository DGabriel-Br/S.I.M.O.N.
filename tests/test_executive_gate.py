from __future__ import annotations

from pathlib import Path

from simon.actions import create_action, transition_action
from simon.cli import main
from simon.executive import decide_next
from simon.executive_gate import describe_current_operation_gate, describe_operation_gate
from simon.file_patch import FilePatchRequest
from simon.goals import Goal, insert_goal
from simon.operation_proposal import propose_file_patch, propose_process_run
from simon.plans import create_plan
from simon.process_binding import ProcessRunRequest
from simon.storage import initialize_storage


def _goal(database_path: Path, title: str) -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"description": "Concluir a operação atual."},
        success_criteria=({"description": "A operação foi verificada."},),
    )
    insert_goal(database_path, goal)
    return goal


def _process_plan(database_path: Path) -> tuple[Goal, str]:
    goal = _goal(database_path, "Executar teste")
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar testes.",
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


def _change_plan(database_path: Path) -> tuple[Goal, str]:
    goal = _goal(database_path, "Corrigir arquivo")
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Corrigir valor no arquivo.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "Correção localizada.",
                "verification": "Arquivo corrigido e salvo.",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )
    return goal, plan.id


def test_process_gate_explains_missing_concrete_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _process_plan(database_path)

    presentation = describe_current_operation_gate(database_path, goal_id=goal.id)

    assert presentation.status == "PROPOSAL_REQUIRED"
    assert presentation.proposal_type == "process.run"
    assert presentation.required_inputs == (
        "executable",
        "arguments",
        "working_directory",
        "timeout_seconds",
    )
    assert presentation.proposal_event_id is None
    assert presentation.materialization_command is not None
    assert "process-propose" in presentation.materialization_command
    assert goal.id in presentation.materialization_command
    assert presentation.materialization_examples == (
        "Rode <executável> [args...] neste projeto",
        "Execute <executável> [args...] neste projeto",
    )


def test_process_gate_presents_current_proposal_ready_for_authorization(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _process_plan(database_path)
    request = ProcessRunRequest(
        executable="python",
        arguments=("-m", "pytest"),
        working_directory=str(tmp_path),
        timeout_seconds=30.0,
    )
    proposal = propose_process_run(database_path, goal_id=goal.id, request=request)

    presentation = describe_current_operation_gate(database_path, goal_id=goal.id)

    assert presentation.status == "READY_FOR_AUTHORIZATION"
    assert presentation.proposal_event_id == proposal.event.id
    assert presentation.required_inputs == ()
    assert presentation.authorization_examples == ("sim", "autorizo", "pode executar")
    values = {field.label: field.value for field in presentation.details}
    assert values["Executável"] == "python"
    assert values["argv"] == "python -m pytest"
    assert values["Diretório"] == str(tmp_path)


def test_file_patch_gate_presents_exact_change_without_modifying_file(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _ = _change_plan(database_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "script.py"
    target.write_text("valor = 1\n", encoding="utf-8")
    proposal = propose_file_patch(
        database_path,
        goal_id=goal.id,
        request=FilePatchRequest(
            workspace=str(workspace),
            relative_path="script.py",
            expected_text="valor = 1",
            replacement_text="valor = 2",
        ),
    )

    presentation = describe_current_operation_gate(database_path, goal_id=goal.id)

    assert presentation.status == "READY_FOR_AUTHORIZATION"
    assert presentation.proposal_event_id == proposal.event.id
    values = {field.label: field.value for field in presentation.details}
    assert values["Arquivo"] == "script.py"
    assert values["Trecho esperado"] == "valor = 1"
    assert values["Substituição"] == "valor = 2"
    assert target.read_text(encoding="utf-8") == "valor = 1\n"


def test_process_retry_gate_explains_action_and_required_retry_parameters(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id = _process_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_01",
        kind="process.run",
        input_data={},
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "FAILED",
        failure={"kind": "start_failed", "message": "falha observada"},
    )

    presentation = describe_current_operation_gate(database_path, goal_id=goal.id)

    assert presentation.status == "PROPOSAL_REQUIRED"
    assert presentation.proposal_type == "process.retry"
    assert presentation.decision.action_id == action.id
    assert presentation.materialization_command is not None
    assert f"process-retry-propose {action.id}" in presentation.materialization_command


def test_analysis_retry_gate_requires_only_model_before_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = _goal(database_path, "Refazer análise")
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar evidência.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A análise foi produzida.",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
        input_data={},
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "FAILED",
        failure={"kind": "model_provider_error", "message": "runtime indisponível"},
    )

    presentation = describe_current_operation_gate(database_path, goal_id=goal.id)

    assert presentation.status == "PROPOSAL_REQUIRED"
    assert presentation.proposal_type == "analysis.retry"
    assert presentation.required_inputs == ("model",)
    assert presentation.materialization_command is not None
    assert action.id in presentation.materialization_command


def test_non_operation_decision_is_not_presented_as_authorization_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    decision = decide_next(database_path)

    presentation = describe_operation_gate(database_path, decision)

    assert presentation.status == "NOT_OPERATION_GATE"
    assert presentation.proposal_event_id is None


def test_executive_gate_cli_explains_how_to_materialize_current_process_gate(
    tmp_path: Path,
    capsys,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, _ = _process_plan(database_path)

    exit_code = main(["--data-dir", str(data_dir), "executive-gate", goal.id])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Estado do gate: PROPOSAL_REQUIRED" in output
    assert "Tipo de proposta: process.run" in output
    assert "Inputs necessários:" in output
    assert "process-propose" in output
    assert "Entradas conversacionais aceitas:" in output
    assert '"Rode <executável> [args...] neste projeto"' in output
    assert "Autorização disponível agora: não" in output


def test_executive_continue_automatically_prints_operation_gate_context(
    tmp_path: Path,
    capsys,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, _ = _process_plan(database_path)

    exit_code = main(["--data-dir", str(data_dir), "executive-continue", goal.id])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Gate operacional:" in output
    assert "Estado do gate: PROPOSAL_REQUIRED" in output
    assert "Comando de materialização:" in output
