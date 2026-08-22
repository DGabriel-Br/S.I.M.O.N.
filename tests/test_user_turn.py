from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from simon.actions import list_actions_for_plan
from simon.cli import main
from simon.events import get_event
from simon.goal_verification import (
    GoalCriterionAssessment,
    GoalEvidenceAssessment,
    assess_goal_outcome,
)
from simon.goals import Goal, get_goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep
from simon.plans import create_plan, list_plans_for_goal
from simon.storage import initialize_storage
from simon.user_ask import dispatch_next_user_ask
from simon.user_ask_verification import UserAskCriterionAssessment
from simon.user_turn import handle_user_turn, interpret_user_turn_intent
from simon.verification import list_verification_results


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


class UserAskSatisfiedProvider:
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
        output = UserAskCriterionAssessment(
            verdict="SATISFIED",
            rationale="A resposta forneceu diretamente a evidência solicitada.",
            missing_information=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


class GoalSatisfiedProvider:
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
        output = GoalEvidenceAssessment(
            criteria=[
                GoalCriterionAssessment(
                    criterion_index=1,
                    verdict="SATISFIED",
                    rationale="A resposta confirmada satisfaz o critério do Goal.",
                    supporting_step_ids=["step_01"],
                )
            ],
            missing_evidence=[],
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


def _waiting_user_ask(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Obter evidência",
        origin="USER",
        desired_state={"description": "A evidência foi recebida."},
        success_criteria=({"description": "O usuário forneceu a evidência solicitada."},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar a evidência ao usuário.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário forneceu a evidência solicitada.",
                "intent_role": "COLLECT",
                "intent_actor": "USER",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)
    return goal, dispatch.action.id


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



def test_turn_intent_does_not_treat_contextual_reply_as_global_intent() -> None:
    assert interpret_user_turn_intent("sim") is None
    assert interpret_user_turn_intent("confirmo") is None
    assert interpret_user_turn_intent("print('ok')") is None


def test_user_input_gate_binds_free_text_to_waiting_action_and_continues(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _waiting_user_ask(database_path)

    receipt = handle_user_turn(
        database_path,
        "print('ok')",
        goal_id=goal.id,
        provider=UserAskSatisfiedProvider(),
        model="fake-model",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "ANSWER"
    assert receipt.effect_type == "user.response"
    assert receipt.effect_id is not None
    response_event = get_event(database_path, receipt.effect_id)
    assert response_event is not None
    assert response_event.kind == "user.response.received"
    assert response_event.source == "user"
    assert response_event.trace_id == receipt.turn_event.id
    assert response_event.payload["action_id"] == action_id
    assert response_event.payload["response"] == "print('ok')"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_USER_CONFIRMATION"
    assert receipt.executive_receipt.final_decision.operation == "verification.confirm"
    assert receipt.routing_event.payload["authority_scope"] == "CURRENT_USER_INPUT_GATE_ONLY"
    assert receipt.routing_event.payload["gate"]["action_id"] == action_id


def test_confirmation_turn_confirms_only_current_action_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _waiting_user_ask(database_path)
    answered = handle_user_turn(
        database_path,
        "evidência concreta",
        goal_id=goal.id,
        provider=UserAskSatisfiedProvider(),
        model="fake-model",
    )
    assert answered.executive_receipt is not None
    assessment_id = answered.executive_receipt.final_decision.verification_id
    assert assessment_id is not None

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.intent == "CONFIRM"
    assert receipt.effect_type == "verification.confirmed"
    assert receipt.effect_id is not None
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    confirmed = results[-1]
    assert confirmed.id == receipt.effect_id
    assert confirmed.status == "VERIFIED"
    assert confirmed.observed["confirmed_assessment_id"] == assessment_id
    confirmation_event_id = confirmed.observed["confirmation_event_id"]
    assert isinstance(confirmation_event_id, str)
    confirmation_event = get_event(database_path, confirmation_event_id)
    assert confirmation_event is not None
    assert confirmation_event.source == "user"
    assert confirmation_event.trace_id == receipt.turn_event.id
    assert receipt.routing_event.payload["authority_scope"] == "CURRENT_CONFIRMATION_GATE_ONLY"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "MODEL_REQUIRED"
    assert receipt.executive_receipt.final_decision.operation == "goal.assess"


def test_goal_confirmation_turn_completes_only_current_satisfied_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _waiting_user_ask(database_path)
    answered = handle_user_turn(
        database_path,
        "evidência concreta",
        goal_id=goal.id,
        provider=UserAskSatisfiedProvider(),
        model="fake-model",
    )
    assert answered.executive_receipt is not None
    confirmed = handle_user_turn(database_path, "sim", goal_id=goal.id)
    assert confirmed.executive_receipt is not None
    assert confirmed.executive_receipt.final_decision.operation == "goal.assess"

    assessment = assess_goal_outcome(
        database_path,
        GoalSatisfiedProvider(),
        model="fake-model",
        goal_id=goal.id,
    )
    assert assessment.overall_verdict == "SATISFIED"

    receipt = handle_user_turn(database_path, "confirmo", goal_id=goal.id)

    assert receipt.status == "ROUTED"
    assert receipt.intent == "CONFIRM"
    assert receipt.effect_type == "goal.completed"
    assert receipt.effect_id == goal.id
    persisted = get_goal(database_path, goal.id)
    assert persisted is not None
    assert persisted.status == "COMPLETED"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "DONE"
    assert receipt.executive_receipt.final_decision.outcome == "DONE"

    goal_results = list_verification_results(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
    )
    final_verification = goal_results[-1]
    confirmation_event_id = final_verification.observed["confirmation_event_id"]
    assert isinstance(confirmation_event_id, str)
    confirmation_event = get_event(database_path, confirmation_event_id)
    assert confirmation_event is not None
    assert confirmation_event.trace_id == receipt.turn_event.id


def test_affirmative_turn_does_not_authorize_operation_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan_id = _process_plan(database_path, goal.id)

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.intent is None
    assert receipt.effect_type is None
    assert receipt.executive_receipt is None
    assert receipt.routing_event.payload["reason_code"] == (
        "operation_authorization_requires_explicit_command"
    )
    gate = receipt.routing_event.payload["gate"]
    assert gate["outcome"] == "NEEDS_OPERATION_AUTHORIZATION"
    assert gate["operation"] == "plan.run"
    assert list_actions_for_plan(database_path, plan_id) == ()


def test_non_explicit_text_does_not_confirm_semantic_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _waiting_user_ask(database_path)
    answered = handle_user_turn(
        database_path,
        "evidência concreta",
        goal_id=goal.id,
        provider=UserAskSatisfiedProvider(),
        model="fake-model",
    )
    assert answered.executive_receipt is not None
    assessment_id = answered.executive_receipt.final_decision.verification_id
    assert assessment_id is not None

    receipt = handle_user_turn(database_path, "ok", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "explicit_confirmation_required"
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    assert results[-1].id == assessment_id
    assert results[-1].status == "ASSESSED"
