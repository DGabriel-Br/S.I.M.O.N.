from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from simon.actions import list_actions_for_plan
from simon.attention import AttentionSignals, assess_observation_attention, open_attention_item
from simon.cli import main
from simon.cognition import GoalProposal, UserInputInterpretation
from simon.events import get_event
from simon.executive import decide_next
from simon.goal_verification import (
    GoalCriterionAssessment,
    GoalEvidenceAssessment,
    assess_goal_outcome,
)
from simon.goals import Goal, get_goal, insert_goal, list_open_goals
from simon.model_provider import StructuredModelResult
from simon.perception import record_observation
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


class GoalIntakeProvider:
    def __init__(self, *, intent: str = "REQUEST") -> None:
        self.intent = intent

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
        if response_model is UserInputInterpretation:
            output = UserInputInterpretation(
                intent=self.intent,
                objective=(
                    "corrigir a falha do script" if self.intent == "REQUEST" else None
                ),
                entity_mentions=[],
                ambiguities=[],
            )
        elif response_model is GoalProposal:
            if self.intent != "REQUEST":
                raise AssertionError("propose_goal não deveria ser chamado para outro intent")
            output = GoalProposal(
                title="Corrigir falha do script",
                desired_state="O script executa sem reproduzir a falha relatada.",
                success_criteria=["A falha original não é reproduzida."],
                open_questions=[],
            )
        else:
            raise AssertionError(f"response_model inesperado: {response_model}")

        assert isinstance(output, response_model)
        return StructuredModelResult(
            model=model,
            output=output,
            prompt_eval_count=20,
            eval_count=12,
            total_duration_ns=1_500_000_000,
        )

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
    assert receipt.routing_event.payload["reason_code"] == "operation_proposal_required"
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


def test_goal_selection_by_ordinal_persists_focus_without_executing_work(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _goal(database_path, "Goal A")
    _goal(database_path, "Goal B")
    initial = decide_next(database_path)
    selected_id = initial.goal_candidates[0].goal_id

    receipt = handle_user_turn(database_path, "o primeiro")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "SELECT"
    assert receipt.effect_type == "goal.focus"
    assert receipt.effect_id is not None
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.goal_id == selected_id
    assert receipt.routing_event.payload["authority_scope"] == "FOREGROUND_GOAL_SELECTION_ONLY"
    assert list_plans_for_goal(database_path, selected_id) == ()


def test_goal_selection_accepts_unique_title_without_goal_id(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    selected = _goal(database_path, "Revisar integração aérea")
    _goal(database_path, "Conferir documentação")

    receipt = handle_user_turn(database_path, "Escolho o Goal Revisar integração aérea")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "SELECT"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.goal_id == selected.id


def test_goal_selection_rejects_ambiguous_duplicate_title(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _goal(database_path, "Revisar processo")
    _goal(database_path, "Revisar processo")

    receipt = handle_user_turn(database_path, "Revisar processo")

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "goal_selection_not_resolved"
    gate = receipt.routing_event.payload["gate"]
    assert isinstance(gate, dict)
    assert len(gate["goal_candidates"]) == 2


def test_goal_selection_rejects_ordinal_outside_current_candidates(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _goal(database_path, "Goal A")
    _goal(database_path, "Goal B")

    receipt = handle_user_turn(database_path, "o terceiro")

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "goal_selection_not_resolved"


def test_continue_without_goal_id_reuses_persisted_foreground_focus(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _goal(database_path, "Goal A")
    second = _goal(database_path, "Goal B")
    initial = decide_next(database_path)
    selected_id = initial.goal_candidates[0].goal_id
    other_id = first.id if selected_id == second.id else second.id

    selection = handle_user_turn(database_path, "primeiro")
    assert selection.status == "ROUTED"

    receipt = handle_user_turn(
        database_path,
        "continue",
        provider=PlanningProvider(),
        model="fake-model",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "CONTINUE"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.goal_id == selected_id
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_USER_INPUT"
    assert len(list_plans_for_goal(database_path, selected_id)) == 1
    assert list_plans_for_goal(database_path, other_id) == ()


def test_user_turn_cli_selects_goal_by_ordinal_without_executing_it(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _goal(database_path, "Goal A")
    _goal(database_path, "Goal B")
    selected_id = decide_next(database_path).goal_candidates[1].goal_id

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "user-turn",
            "o",
            "segundo",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "User turn: ROUTED" in output
    assert "Intent: SELECT" in output
    assert "Efeito do gate: goal.focus" in output
    assert "Transições executadas: 0" in output
    assert f"Goal: {selected_id}" in output


def test_goal_selection_accepts_numeric_reference_from_presented_order(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _goal(database_path, "Goal A")
    _goal(database_path, "Goal B")
    selected_id = decide_next(database_path).goal_candidates[1].goal_id

    receipt = handle_user_turn(database_path, "goal 2")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "SELECT"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.goal_id == selected_id


def test_explicit_goal_focus_switch_replaces_current_focus_without_executing_work(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    current = _goal(database_path, "Corrigir script")
    target = _goal(database_path, "Revisar documentação")

    selected = handle_user_turn(database_path, "Corrigir script")
    assert selected.status == "ROUTED"
    assert selected.executive_receipt is not None
    assert selected.executive_receipt.final_decision.goal_id == current.id

    receipt = handle_user_turn(
        database_path,
        "Troque para o Goal Revisar documentação",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "SELECT"
    assert receipt.effect_type == "goal.focus"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.goal_id == target.id
    assert list_plans_for_goal(database_path, current.id) == ()
    assert list_plans_for_goal(database_path, target.id) == ()

    next_decision = decide_next(database_path)
    assert next_decision.goal_id == target.id


def test_explicit_goal_focus_switch_is_not_consumed_as_current_user_answer(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    current, action_id = _waiting_user_ask(database_path)
    target = _goal(database_path, "Revisar documentação")

    selected = handle_user_turn(database_path, "Obter evidência")
    assert selected.status == "ROUTED"
    assert decide_next(database_path).goal_id == current.id
    assert decide_next(database_path).outcome == "NEEDS_USER_INPUT"

    receipt = handle_user_turn(
        database_path,
        "Mude para o objetivo Revisar documentação",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "SELECT"
    assert receipt.effect_type == "goal.focus"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.goal_id == target.id

    current_action = next(
        action
        for plan in list_plans_for_goal(database_path, current.id)
        for action in list_actions_for_plan(database_path, plan.id)
        if action.id == action_id
    )
    assert current_action.status == "WAITING"


def test_explicit_goal_focus_switch_requires_unique_open_title(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    current = _goal(database_path, "Corrigir script")
    _goal(database_path, "Revisar processo")
    _goal(database_path, "Revisar processo")

    selected = handle_user_turn(database_path, "Corrigir script")
    assert selected.status == "ROUTED"

    receipt = handle_user_turn(database_path, "Foque no Goal Revisar processo")

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "goal_focus_switch_not_resolved"
    assert decide_next(database_path).goal_id == current.id


def test_explicit_goal_id_wins_over_conflicting_conversational_focus_switch(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    current = _goal(database_path, "Corrigir script")
    target = _goal(database_path, "Revisar documentação")

    selected = handle_user_turn(database_path, "Corrigir script")
    assert selected.status == "ROUTED"

    receipt = handle_user_turn(
        database_path,
        "Troque para o Goal Revisar documentação",
        goal_id=current.id,
    )

    assert receipt.status == "UNSUPPORTED"
    assert (
        receipt.routing_event.payload["reason_code"]
        == "goal_focus_switch_conflicts_with_explicit_goal"
    )
    assert decide_next(database_path).goal_id == current.id
    assert decide_next(database_path, goal_id=target.id).goal_id == target.id


def test_idle_request_materializes_goal_proposal_without_accepting_it(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    receipt = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "PROPOSE"
    assert receipt.effect_type == "goal.proposal"
    assert receipt.effect_id is not None
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.outcome == "DONE"
    assert receipt.executive_receipt.final_decision.reason_code == "no_open_goal"
    assert list_open_goals(database_path) == ()

    proposal_event = get_event(database_path, receipt.effect_id)
    assert proposal_event is not None
    assert proposal_event.kind == "cognition.goal_proposal.completed"
    assert proposal_event.source == "cognition"
    assert proposal_event.trace_id == receipt.turn_event.id
    raw_proposal = proposal_event.payload["proposal"]
    assert isinstance(raw_proposal, dict)
    assert raw_proposal["title"] == "Corrigir falha do script"
    assert receipt.routing_event.payload["authority_scope"] == "GOAL_PROPOSAL_ONLY"
    assert receipt.routing_event.payload["proposal_event_id"] == proposal_event.id


def test_idle_request_requires_explicit_model_for_goal_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    receipt = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
    )

    assert receipt.status == "UNSUPPORTED"
    assert receipt.intent is None
    assert receipt.routing_event.payload["reason_code"] == "goal_proposal_model_required"
    assert list_open_goals(database_path) == ()


def test_idle_non_request_is_interpreted_but_does_not_create_goal_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    receipt = handle_user_turn(
        database_path,
        "Por que esse script está falhando?",
        provider=GoalIntakeProvider(intent="QUESTION"),
        model="fake-model",
    )

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "new_goal_request_required"
    assert list_open_goals(database_path) == ()


def test_new_goal_request_does_not_bypass_existing_foreground_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan_id = _process_plan(database_path, goal.id)

    receipt = handle_user_turn(
        database_path,
        "Crie um novo relatório",
        goal_id=goal.id,
        provider=GoalIntakeProvider(),
        model="fake-model",
    )

    assert receipt.status == "UNSUPPORTED"
    assert (
        receipt.routing_event.payload["reason_code"]
        == "explicit_operation_authorization_required"
    )
    assert list_actions_for_plan(database_path, plan_id) == ()
    assert len(list_open_goals(database_path)) == 1


def test_user_turn_cli_materializes_idle_goal_proposal(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    class FakeProvider(GoalIntakeProvider):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    exit_code = main(
        [
            "--data-dir",
            str(tmp_path),
            "user-turn",
            "--model",
            "fake-model",
            "Corrija",
            "a",
            "falha",
            "do",
            "script",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "User turn: ROUTED" in output
    assert "Intent: PROPOSE" in output
    assert "Efeito do gate: goal.proposal evt_" in output
    assert "Título: Corrigir falha do script" in output
    assert "Goal persistido: não" in output
    assert "Para aceitar: uv run simon goal-accept evt_" in output


def test_pending_goal_proposal_is_accepted_by_second_user_turn(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposed = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert proposed.effect_id is not None

    receipt = handle_user_turn(database_path, "sim")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "ACCEPT"
    assert receipt.effect_type == "goal.accepted"
    assert receipt.effect_id is not None
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.outcome == "PROCEED"
    assert receipt.executive_receipt.final_decision.operation == "plan.propose"
    assert receipt.routing_event.payload["authority_scope"] == (
        "CURRENT_GOAL_PROPOSAL_ACCEPTANCE_ONLY"
    )
    assert receipt.routing_event.payload["proposal_event_id"] == proposed.effect_id

    open_goals = list_open_goals(database_path)
    assert len(open_goals) == 1
    assert open_goals[0].id == receipt.effect_id
    assert open_goals[0].title == "Corrigir falha do script"


def test_pending_goal_proposal_is_rejected_without_creating_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposed = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert proposed.effect_id is not None

    receipt = handle_user_turn(database_path, "não")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "REJECT"
    assert receipt.effect_type == "goal.rejected"
    assert receipt.effect_id is not None
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.transitions_executed == 0
    assert receipt.executive_receipt.final_decision.outcome == "DONE"
    assert receipt.executive_receipt.final_decision.reason_code == "no_open_goal"
    assert list_open_goals(database_path) == ()

    rejection_event = get_event(database_path, receipt.effect_id)
    assert rejection_event is not None
    assert rejection_event.kind == "goal.proposal.rejected"
    assert rejection_event.source == "user"
    assert rejection_event.trace_id == receipt.turn_event.id
    assert rejection_event.payload["proposal_event_id"] == proposed.effect_id


def test_pending_goal_proposal_blocks_unrelated_new_request(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposed = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert proposed.effect_id is not None

    receipt = handle_user_turn(
        database_path,
        "Crie um relatório novo",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "goal_proposal_response_required"
    assert list_open_goals(database_path) == ()

    from simon.goal_intake import find_latest_pending_conversational_goal_proposal

    pending = find_latest_pending_conversational_goal_proposal(database_path)
    assert pending is not None
    assert pending.id == proposed.effect_id


def test_rejected_goal_proposal_allows_new_idle_request(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert first.effect_id is not None
    rejected = handle_user_turn(database_path, "descarto")
    assert rejected.intent == "REJECT"

    second = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )

    assert second.status == "ROUTED"
    assert second.intent == "PROPOSE"
    assert second.effect_type == "goal.proposal"
    assert second.effect_id is not None
    assert second.effect_id != first.effect_id


def test_user_turn_cli_accepts_pending_goal_proposal(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    class FakeProvider(GoalIntakeProvider):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "user-turn",
            "--model",
            "fake-model",
            "Corrija",
            "a",
            "falha",
            "do",
            "script",
        ]
    ) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    assert main(["--data-dir", str(tmp_path), "user-turn", "sim"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert "User turn: ROUTED" in output
    assert "Intent: ACCEPT" in output
    assert "Efeito do gate: goal.accepted gol_" in output
    assert "Transições executadas: 0" in output
    assert "Goal persistido: sim" in output


def test_pending_goal_proposal_blocks_continue_until_answered(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposed = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert proposed.effect_id is not None

    receipt = handle_user_turn(database_path, "continue")

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "goal_proposal_response_required"
    assert list_open_goals(database_path) == ()

    from simon.goal_intake import find_latest_pending_conversational_goal_proposal

    pending = find_latest_pending_conversational_goal_proposal(database_path)
    assert pending is not None
    assert pending.id == proposed.effect_id


def _pending_attend(database_path: Path) -> None:
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="item de atenção pendente",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    open_attention_item(database_path, attention_event_id=assessment.event.id)


def test_user_foreground_request_can_propose_goal_while_attend_is_pending(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _pending_attend(database_path)

    receipt = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "PROPOSE"
    assert receipt.effect_type == "goal.proposal"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.outcome == "NEEDS_ATTENTION_REVIEW"
    assert list_open_goals(database_path) == ()


def test_pending_goal_proposal_response_outranks_idle_attend_review(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _pending_attend(database_path)
    proposed = handle_user_turn(
        database_path,
        "Corrija a falha do script",
        provider=GoalIntakeProvider(),
        model="fake-model",
    )
    assert proposed.effect_type == "goal.proposal"

    receipt = handle_user_turn(database_path, "sim")

    assert receipt.status == "ROUTED"
    assert receipt.intent == "ACCEPT"
    assert receipt.effect_type == "goal.accepted"
    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.final_decision.outcome == "PROCEED"
    assert receipt.executive_receipt.final_decision.operation == "plan.propose"
    assert len(list_open_goals(database_path)) == 1
