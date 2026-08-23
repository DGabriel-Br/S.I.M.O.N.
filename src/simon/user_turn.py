from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.assessment_confirmation import confirm_action_assessment
from simon.events import Event, append_event
from simon.executive import ExecutiveDecision, decide_next
from simon.executive_runner import ExecutiveContinueReceipt, run_executive_until_gate
from simon.file_patch import execute_next_file_patch
from simon.goal_completion import complete_goal_from_assessment
from simon.model_provider import ModelProvider
from simon.operation_proposal import (
    find_current_file_patch_proposal,
    find_current_process_run_proposal,
)
from simon.process_execution import execute_next_process_run
from simon.user_ask import answer_user_ask

UserTurnIntent = Literal["CONTINUE", "ANSWER", "CONFIRM", "AUTHORIZE"]
UserTurnStatus = Literal["ROUTED", "UNSUPPORTED", "FAILED"]
UserTurnEffectType = Literal[
    "user.response",
    "verification.confirmed",
    "goal.completed",
    "process.run",
    "file.patch",
]

_CONTINUE_UTTERANCES = {
    "continue",
    "continue esse goal",
    "continue este goal",
    "continue o goal",
    "continue com esse goal",
    "continue com este goal",
    "continue com o goal",
    "continue esse objetivo",
    "continue este objetivo",
    "continue o objetivo",
    "continue com esse objetivo",
    "continue com este objetivo",
    "continue com o objetivo",
}

_CONFIRM_UTTERANCES = {
    "sim",
    "confirmo",
    "confirmado",
    "sim confirmo",
    "pode confirmar",
}

_AUTHORIZE_UTTERANCES = {
    "sim",
    "autorizo",
    "pode executar",
    "pode rodar",
    "sim pode executar",
    "pode alterar",
    "pode aplicar",
    "pode modificar",
}


@dataclass(frozen=True, slots=True)
class UserTurnReceipt:
    status: UserTurnStatus
    turn_event: Event
    intent: UserTurnIntent | None
    routing_event: Event
    executive_receipt: ExecutiveContinueReceipt | None = None
    effect_type: UserTurnEffectType | None = None
    effect_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status == "ROUTED" and (self.intent is None or self.executive_receipt is None):
            raise ValueError("ROUTED exige intent e resultado do Executive")
        if self.status == "ROUTED" and self.error is not None:
            raise ValueError("ROUTED não pode declarar erro")
        if self.status != "ROUTED" and self.executive_receipt is not None:
            raise ValueError(f"{self.status} não pode declarar resultado do Executive")
        if self.status == "UNSUPPORTED" and self.intent is not None:
            raise ValueError("UNSUPPORTED não pode declarar intent")
        if self.status == "UNSUPPORTED" and self.error is not None:
            raise ValueError("UNSUPPORTED não pode declarar erro")
        if self.status == "FAILED" and not self.error:
            raise ValueError("FAILED exige mensagem de erro")
        if (self.effect_type is None) != (self.effect_id is None):
            raise ValueError("effect_type e effect_id devem ser declarados juntos")
        if self.status != "ROUTED" and self.effect_type is not None:
            raise ValueError(f"{self.status} não pode declarar efeito de gate")
        if self.intent == "CONTINUE" and self.effect_type is not None:
            raise ValueError("CONTINUE não pode declarar efeito de gate")
        if (
            self.status == "ROUTED"
            and self.intent in {"ANSWER", "CONFIRM", "AUTHORIZE"}
            and self.effect_type is None
        ):
            raise ValueError(f"{self.intent} exige efeito de gate persistido")


def handle_user_turn(
    database_path: Path,
    text: str,
    *,
    goal_id: str | None = None,
    provider: ModelProvider | None = None,
    model: str | None = None,
    max_transitions: int = 32,
) -> UserTurnReceipt:
    """Registra um turno humano e aplica somente o significado permitido pelo gate atual."""
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("turno do usuário não pode ser vazio")
    if max_transitions <= 0:
        raise ValueError("max_transitions deve ser maior que zero")

    turn_event = Event.create(
        kind="user.turn.received",
        source="user",
        payload={
            "text": normalized_text,
            "requested_goal_id": goal_id,
        },
        goal_id=goal_id,
    )
    append_event(database_path, turn_event)

    intent = interpret_user_turn_intent(normalized_text)
    if intent == "CONTINUE":
        return _route_continue(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    try:
        decision = decide_next(database_path, goal_id=goal_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent=None,
            goal_id=goal_id,
            error=str(exc),
            reason_code="gate_lookup_failed",
        )

    if decision.outcome == "NEEDS_USER_INPUT" and decision.operation == "action.answer":
        return _route_user_answer(
            database_path,
            turn_event=turn_event,
            decision=decision,
            response=normalized_text,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    if (
        decision.outcome == "NEEDS_USER_CONFIRMATION"
        and not _is_explicit_confirmation(normalized_text)
    ):
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=decision.goal_id or goal_id,
            reason_code="explicit_confirmation_required",
            current_decision=decision,
        )
    if decision.outcome == "NEEDS_USER_CONFIRMATION":
        return _route_confirmation(
            database_path,
            turn_event=turn_event,
            decision=decision,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    if decision.outcome == "NEEDS_OPERATION_AUTHORIZATION":
        return _route_operation_authorization_turn(
            database_path,
            turn_event=turn_event,
            decision=decision,
            text=normalized_text,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    return _unsupported_turn(
        database_path,
        turn_event=turn_event,
        goal_id=decision.goal_id or goal_id,
        reason_code="unsupported_intent",
        current_decision=decision,
    )


def interpret_user_turn_intent(text: str) -> UserTurnIntent | None:
    normalized = _normalize_turn_text(text)
    if normalized in _CONTINUE_UTTERANCES:
        return "CONTINUE"
    return None


def _route_continue(
    database_path: Path,
    *,
    turn_event: Event,
    goal_id: str | None,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    try:
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="CONTINUE",
            goal_id=goal_id,
            error=str(exc),
            reason_code="continue_routing_failed",
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="CONTINUE",
        executive_receipt=executive_receipt,
        authority_scope="EXECUTIVE_SAFE_CONTINUATION",
        goal_id=executive_receipt.final_decision.goal_id or goal_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="CONTINUE",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
    )


def _route_user_answer(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    response: str,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    action_id = _required_decision_value(decision.action_id, "action_id", decision)
    goal_id = _required_decision_value(decision.goal_id, "goal_id", decision)
    try:
        answer = answer_user_ask(
            database_path,
            action_id=action_id,
            response=response,
            trace_id=turn_event.id,
        )
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="ANSWER",
            goal_id=goal_id,
            error=str(exc),
            reason_code="user_answer_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="ANSWER",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_USER_INPUT_GATE_ONLY",
        goal_id=goal_id,
        current_decision=decision,
        effect_type="user.response",
        effect_id=answer.response_event_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="ANSWER",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type="user.response",
        effect_id=answer.response_event_id,
    )


def _route_confirmation(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    verification_id = _required_decision_value(
        decision.verification_id,
        "verification_id",
        decision,
    )
    goal_id = _required_decision_value(decision.goal_id, "goal_id", decision)

    try:
        if decision.operation == "verification.confirm":
            confirmation = confirm_action_assessment(
                database_path,
                assessment_verification_id=verification_id,
                trace_id=turn_event.id,
            )
            effect_type: UserTurnEffectType = "verification.confirmed"
            effect_id = confirmation.verification.id
        elif decision.operation == "goal.complete":
            completion = complete_goal_from_assessment(
                database_path,
                assessment_verification_id=verification_id,
                trace_id=turn_event.id,
            )
            effect_type = "goal.completed"
            effect_id = completion.goal.id
        else:
            raise RuntimeError(
                "gate NEEDS_USER_CONFIRMATION não possui operação confirmável conhecida: "
                f"{decision.operation}"
            )

        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="CONFIRM",
            goal_id=goal_id,
            error=str(exc),
            reason_code="confirmation_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="CONFIRM",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_CONFIRMATION_GATE_ONLY",
        goal_id=goal_id,
        current_decision=decision,
        effect_type=effect_type,
        effect_id=effect_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="CONFIRM",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type=effect_type,
        effect_id=effect_id,
    )


def _route_operation_authorization_turn(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    text: str,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    goal_id = decision.goal_id
    if not _is_explicit_operation_authorization(text):
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            reason_code="explicit_operation_authorization_required",
            current_decision=decision,
        )

    if decision.operation == "plan.run" and decision.capability == "process.run":
        process_proposal = find_current_process_run_proposal(database_path, decision)
        if process_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = process_proposal.goal_id
        proposal_event_id = process_proposal.event.id
        try:
            process_execution = execute_next_process_run(
                database_path,
                goal_id=proposal_goal_id,
                request=process_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type: UserTurnEffectType = "process.run"
        effect_id = process_execution.action.id
    elif decision.operation == "plan.patch" and decision.capability == "file.patch":
        patch_proposal = find_current_file_patch_proposal(database_path, decision)
        if patch_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = patch_proposal.goal_id
        proposal_event_id = patch_proposal.event.id
        try:
            patch_execution = execute_next_file_patch(
                database_path,
                goal_id=proposal_goal_id,
                request=patch_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type = "file.patch"
        effect_id = patch_execution.action.id
    else:
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            reason_code="operation_proposal_not_supported",
            current_decision=decision,
        )

    try:
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=proposal_goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="AUTHORIZE",
            goal_id=proposal_goal_id,
            error=str(exc),
            reason_code="operation_authorization_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="AUTHORIZE",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_OPERATION_PROPOSAL_ONLY",
        goal_id=proposal_goal_id,
        current_decision=decision,
        effect_type=effect_type,
        effect_id=effect_id,
        proposal_event_id=proposal_event_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="AUTHORIZE",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type=effect_type,
        effect_id=effect_id,
    )


def _append_routed_event(
    database_path: Path,
    *,
    turn_event: Event,
    intent: UserTurnIntent,
    executive_receipt: ExecutiveContinueReceipt,
    authority_scope: str,
    goal_id: str | None,
    current_decision: ExecutiveDecision | None = None,
    effect_type: UserTurnEffectType | None = None,
    effect_id: str | None = None,
    proposal_event_id: str | None = None,
) -> Event:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "intent": intent,
        "authority_scope": authority_scope,
        "executive_status": executive_receipt.status,
        "transitions_executed": executive_receipt.transitions_executed,
        "final_outcome": executive_receipt.final_decision.outcome,
        "final_operation": executive_receipt.final_decision.operation,
        "final_reason_code": executive_receipt.final_decision.reason_code,
        "transitions": [
            {
                "operation": transition.executed_operation,
                "result_type": transition.result_type,
                "result_id": transition.result_id,
            }
            for transition in executive_receipt.transitions
        ],
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)
    if effect_type is not None and effect_id is not None:
        payload["effect_type"] = effect_type
        payload["effect_id"] = effect_id
    if proposal_event_id is not None:
        payload["proposal_event_id"] = proposal_event_id

    routing_event = Event.create(
        kind="executive.user_turn.routed",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return routing_event


def _unsupported_turn(
    database_path: Path,
    *,
    turn_event: Event,
    goal_id: str | None,
    reason_code: str,
    current_decision: ExecutiveDecision | None = None,
) -> UserTurnReceipt:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "reason_code": reason_code,
        "supported_intents": [
            "CONTINUE",
            "ANSWER_AT_USER_INPUT_GATE",
            "CONFIRM_AT_GATE",
            "AUTHORIZE_CURRENT_PROCESS_PROPOSAL",
        ],
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)

    routing_event = Event.create(
        kind="user.turn.unhandled",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return UserTurnReceipt(
        status="UNSUPPORTED",
        turn_event=turn_event,
        intent=None,
        routing_event=routing_event,
    )


def _failed_turn(
    database_path: Path,
    *,
    turn_event: Event,
    intent: UserTurnIntent | None,
    goal_id: str | None,
    error: str,
    reason_code: str,
    current_decision: ExecutiveDecision | None = None,
) -> UserTurnReceipt:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "intent": intent,
        "reason_code": reason_code,
        "error": error,
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)

    routing_event = Event.create(
        kind="executive.user_turn.failed",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return UserTurnReceipt(
        status="FAILED",
        turn_event=turn_event,
        intent=intent,
        routing_event=routing_event,
        error=error,
    )


def _decision_gate_payload(decision: ExecutiveDecision) -> dict[str, object]:
    return {
        "outcome": decision.outcome,
        "reason_code": decision.reason_code,
        "operation": decision.operation,
        "goal_id": decision.goal_id,
        "plan_id": decision.plan_id,
        "step_id": decision.step_id,
        "action_id": decision.action_id,
        "verification_id": decision.verification_id,
        "capability": decision.capability,
    }


def _required_decision_value(
    value: str | None,
    field: str,
    decision: ExecutiveDecision,
) -> str:
    if value is None or not value.strip():
        raise RuntimeError(
            f"gate {decision.reason_code} não possui {field} necessário para {decision.operation}"
        )
    return value.strip()


def _is_explicit_confirmation(text: str) -> bool:
    return _normalize_turn_text(text) in _CONFIRM_UTTERANCES


def _is_explicit_operation_authorization(text: str) -> bool:
    return _normalize_turn_text(text) in _AUTHORIZE_UTTERANCES


def _normalize_turn_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_punctuation = re.sub(r"[^\w\s]", " ", without_accents)
    return re.sub(r"\s+", " ", without_punctuation).strip()
