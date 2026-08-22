from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.events import Event, append_event
from simon.executive_runner import ExecutiveContinueReceipt, run_executive_until_gate
from simon.model_provider import ModelProvider

UserTurnIntent = Literal["CONTINUE"]
UserTurnStatus = Literal["ROUTED", "UNSUPPORTED", "FAILED"]

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


@dataclass(frozen=True, slots=True)
class UserTurnReceipt:
    status: UserTurnStatus
    turn_event: Event
    intent: UserTurnIntent | None
    routing_event: Event
    executive_receipt: ExecutiveContinueReceipt | None = None
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


def handle_user_turn(
    database_path: Path,
    text: str,
    *,
    goal_id: str | None = None,
    provider: ModelProvider | None = None,
    model: str | None = None,
    max_transitions: int = 32,
) -> UserTurnReceipt:
    """Registra um turno humano e roteia somente intents explicitamente suportados."""
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("turno do usuário não pode ser vazio")
    if max_transitions <= 0:
        raise ValueError("max_transitions deve ser maior que zero")

    intent = interpret_user_turn_intent(normalized_text)
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

    if intent is None:
        routing_event = Event.create(
            kind="user.turn.unhandled",
            source="system",
            payload={
                "turn_event_id": turn_event.id,
                "reason_code": "unsupported_intent",
                "supported_intents": ["CONTINUE"],
            },
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

    try:
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        routing_event = Event.create(
            kind="executive.user_turn.failed",
            source="system",
            payload={
                "turn_event_id": turn_event.id,
                "intent": intent,
                "authority_scope": "EXECUTIVE_SAFE_CONTINUATION",
                "error": str(exc),
            },
            trace_id=turn_event.id,
            goal_id=goal_id,
        )
        append_event(database_path, routing_event)
        return UserTurnReceipt(
            status="FAILED",
            turn_event=turn_event,
            intent=intent,
            routing_event=routing_event,
            error=str(exc),
        )

    routed_goal_id = executive_receipt.final_decision.goal_id or goal_id
    routing_event = Event.create(
        kind="executive.user_turn.routed",
        source="system",
        payload={
            "turn_event_id": turn_event.id,
            "intent": intent,
            "authority_scope": "EXECUTIVE_SAFE_CONTINUATION",
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
        },
        trace_id=turn_event.id,
        goal_id=routed_goal_id,
    )
    append_event(database_path, routing_event)
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent=intent,
        routing_event=routing_event,
        executive_receipt=executive_receipt,
    )


def interpret_user_turn_intent(text: str) -> UserTurnIntent | None:
    normalized = _normalize_turn_text(text)
    if normalized in _CONTINUE_UTTERANCES:
        return "CONTINUE"
    return None


def _normalize_turn_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_punctuation = re.sub(r"[^\w\s]", " ", without_accents)
    return re.sub(r"\s+", " ", without_punctuation).strip()
