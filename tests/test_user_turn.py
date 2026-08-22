from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from simon.actions import list_actions_for_plan
from simon.cli import main
from simon.events import get_event
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep
from simon.plans import create_plan, list_plans_for_goal
from simon.storage import initialize_storage
from simon.user_turn import handle_user_turn, interpret_user_turn_intent


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


def _process_plan(database_path: Path, goal_id: str) -> str:
    plan = create_plan(
        database_path,
        goal_id=goal_id,
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
    return plan.id


def test_turn_intent_recognizes_only_bounded_continue_phrases() -> None:
    assert interpret_user_turn_intent("Continue esse Goal.") == "CONTINUE"
    assert interpret_user_turn_intent("  CONTINUE com este objetivo!  ") == "CONTINUE"
    assert interpret_user_turn_intent("pode continuar") is None
    assert interpret_user_turn_intent("execute tudo") is None


def test_continue_turn_records_provenance_and_runs_safe_chain(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    receipt = handle_user_turn(
        database_path,
        "Continue esse Goal.",
        goal_id=goal.id,
        provider=PlanningProvider(),
        model="fake-model",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "CONTINUE"
    assert receipt.turn_event.kind == "user.turn.received"
    assert receipt.turn_event.source == "user"
    assert receipt.turn_event.payload["text"] == "Continue esse Goal."
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "STOPPED"
    assert [item.executed_operation for item in receipt.executive_receipt.transitions] == [
        "plan.propose",
        "plan.materialize",
        "plan.ask",
    ]
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_USER_INPUT"
    assert len(list_plans_for_goal(database_path, goal.id)) == 1

    persisted_turn = get_event(database_path, receipt.turn_event.id)
    persisted_route = get_event(database_path, receipt.routing_event.id)
    assert persisted_turn is not None
    assert persisted_turn.source == "user"
    assert persisted_route is not None
    assert persisted_route.source == "system"
    assert persisted_route.trace_id == receipt.turn_event.id
    assert persisted_route.payload["turn_event_id"] == receipt.turn_event.id
    assert persisted_route.payload["intent"] == "CONTINUE"
    assert persisted_route.payload["authority_scope"] == "EXECUTIVE_SAFE_CONTINUATION"
    assert persisted_route.payload["transitions_executed"] == 3


def test_continue_turn_does_not_authorize_process_run(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan_id = _process_plan(database_path, goal.id)

    receipt = handle_user_turn(database_path, "continue", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "STOPPED"
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert receipt.executive_receipt.final_decision.operation == "plan.run"
    assert list_actions_for_plan(database_path, plan_id) == ()
    assert receipt.routing_event.payload["authority_scope"] == "EXECUTIVE_SAFE_CONTINUATION"


def test_unsupported_turn_is_persisted_but_executes_nothing(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan_id = _process_plan(database_path, goal.id)

    receipt = handle_user_turn(database_path, "execute tudo", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.intent is None
    assert receipt.executive_receipt is None
    assert receipt.turn_event.kind == "user.turn.received"
    assert receipt.turn_event.source == "user"
    assert receipt.routing_event.kind == "user.turn.unhandled"
    assert receipt.routing_event.trace_id == receipt.turn_event.id
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_continue_turn_preserves_goal_selection_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _goal(database_path, "Goal A")
    second = _goal(database_path, "Goal B")

    receipt = handle_user_turn(database_path, "continue esse Goal")

    assert receipt.status == "ROUTED"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "STOPPED"
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_GOAL_SELECTION"
    assert {item.goal_id for item in receipt.executive_receipt.final_decision.goal_candidates} == {
        first.id,
        second.id,
    }


def test_continue_turn_with_invalid_explicit_goal_records_failed_route(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    receipt = handle_user_turn(database_path, "continue", goal_id="gol_inexistente")

    assert receipt.status == "FAILED"
    assert receipt.intent == "CONTINUE"
    assert receipt.executive_receipt is None
    assert receipt.error is not None
    assert "goal" in receipt.error.casefold()
    assert receipt.routing_event.kind == "executive.user_turn.failed"
    assert receipt.routing_event.trace_id == receipt.turn_event.id


def test_user_turn_cli_stops_at_operation_authorization(tmp_path: Path, capsys: object) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _process_plan(database_path, goal.id)

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "user-turn",
            "--goal-id",
            goal.id,
            "continue",
            "esse",
            "Goal",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "User turn: ROUTED" in output
    assert "Intent: CONTINUE" in output
    assert "Executive continue: STOPPED" in output
    assert "Transições executadas: 0" in output
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.run" in output
