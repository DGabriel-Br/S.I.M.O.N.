from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from simon.cli import main
from simon.executive_runner import run_executive_until_gate
from simon.goals import Goal, insert_goal, transition_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep
from simon.plans import create_plan, list_plans_for_goal
from simon.storage import initialize_storage


class PlanningProvider:
    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        output = PlanIntentDraft(
            summary="Coletar uma evidência diretamente com o usuário.",
            steps=[
                PlanIntentStep(
                    subject="mensagem de erro observada",
                    role="COLLECT",
                    source="USER",
                    verification="o usuário informou a mensagem de erro",
                )
            ],
            open_questions=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def _goal(database_path: Path, title: str = "Investigar falha") -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"description": "A falha foi compreendida."},
        success_criteria=({"description": "Existe evidência suficiente."},),
    )
    insert_goal(database_path, goal)
    return goal


def test_continue_executes_safe_chain_until_user_input_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    receipt = run_executive_until_gate(
        database_path,
        goal_id=goal.id,
        provider=PlanningProvider(),
        model="fake-model",
    )

    assert receipt.status == "STOPPED"
    assert [item.executed_operation for item in receipt.transitions] == [
        "plan.propose",
        "plan.materialize",
        "plan.ask",
    ]
    assert receipt.transitions_executed == 3
    assert receipt.final_decision.outcome == "NEEDS_USER_INPUT"
    assert receipt.final_decision.operation == "action.answer"
    assert len(list_plans_for_goal(database_path, goal.id)) == 1


def test_continue_respects_transition_limit_before_next_safe_operation(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    receipt = run_executive_until_gate(
        database_path,
        goal_id=goal.id,
        provider=PlanningProvider(),
        model="fake-model",
        max_transitions=2,
    )

    assert receipt.status == "LIMIT_REACHED"
    assert receipt.transitions_executed == 2
    assert [item.executed_operation for item in receipt.transitions] == [
        "plan.propose",
        "plan.materialize",
    ]
    assert receipt.final_decision.outcome == "PROCEED"
    assert receipt.final_decision.operation == "plan.ask"


def test_continue_does_not_cross_operation_authorization(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar comando externo",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "execução observada",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )

    receipt = run_executive_until_gate(database_path, goal_id=goal.id)

    assert receipt.status == "STOPPED"
    assert receipt.transitions_executed == 0
    assert receipt.final_decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert receipt.final_decision.operation == "plan.run"


def test_continue_stops_when_model_is_required(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar evidência",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "análise concluída",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
        ),
    )

    receipt = run_executive_until_gate(database_path, goal_id=goal.id)

    assert receipt.status == "MODEL_REQUIRED"
    assert receipt.transitions_executed == 0
    assert receipt.final_decision.outcome == "PROCEED"
    assert receipt.final_decision.operation == "plan.analyze"
    assert receipt.final_decision.requires_model is True


def test_continue_reports_done_without_executing_transition(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    transition_goal(database_path, goal.id, "COMPLETED")

    receipt = run_executive_until_gate(database_path, goal_id=goal.id)

    assert receipt.status == "DONE"
    assert receipt.transitions_executed == 0
    assert receipt.final_decision.outcome == "DONE"
    assert receipt.final_decision.operation is None


def test_executive_continue_cli_stops_at_authorization_gate(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar comando externo",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "execução observada",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )

    exit_code = main(["--data-dir", str(tmp_path), "executive-continue", goal.id])

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Executive continue: STOPPED" in output
    assert "Transições executadas: 0" in output
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.run" in output
