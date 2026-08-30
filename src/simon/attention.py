from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from simon.events import Event, append_event, get_event
from simon.perception import Observation, get_observation

AttentionDestination = Literal["IGNORE", "RECORD", "UPDATE_WORLD", "ATTEND", "INTERRUPT"]


@dataclass(frozen=True, slots=True)
class AttentionItem:
    event: Event
    assessment_event_id: str
    observation_event_id: str
    summary: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttentionItemOpening:
    item: AttentionItem
    created: bool


@dataclass(frozen=True, slots=True)
class AttentionSignals:
    urgent: bool = False
    risk: bool = False
    goal_relevant: bool = False
    subscribed: bool = False
    world_change: bool = False
    known_noise: bool = False


@dataclass(frozen=True, slots=True)
class AttentionDecision:
    destination: AttentionDestination
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttentionAssessment:
    observation: Observation
    decision: AttentionDecision
    event: Event


def decide_attention(signals: AttentionSignals) -> AttentionDecision:
    """Classifica uma observação por regras pequenas e explicitamente ordenadas."""
    if signals.urgent or signals.risk:
        reasons = tuple(
            reason
            for enabled, reason in (
                (signals.urgent, "urgent"),
                (signals.risk, "risk"),
            )
            if enabled
        )
        return AttentionDecision(destination="INTERRUPT", reasons=reasons)

    if signals.goal_relevant or signals.subscribed:
        reasons = tuple(
            reason
            for enabled, reason in (
                (signals.goal_relevant, "goal_relevant"),
                (signals.subscribed, "subscribed"),
            )
            if enabled
        )
        return AttentionDecision(destination="ATTEND", reasons=reasons)

    if signals.world_change:
        return AttentionDecision(destination="UPDATE_WORLD", reasons=("world_change",))

    if signals.known_noise:
        return AttentionDecision(destination="IGNORE", reasons=("known_noise",))

    return AttentionDecision(destination="RECORD", reasons=("no_escalation_signal",))


def assess_observation_attention(
    database_path: Path,
    *,
    observation_event_id: str,
    signals: AttentionSignals,
) -> AttentionAssessment:
    """Persiste a decisão de Attention sem aplicar o destino ao World ou Executive."""
    observation = get_observation(database_path, observation_event_id)
    if observation is None:
        raise ValueError(f"observation não encontrada: {observation_event_id}")

    decision = decide_attention(signals)
    event = Event.create(
        kind="attention.assessed",
        source="attention",
        payload={
            "observation_event_id": observation.event.id,
            "destination": decision.destination,
            "signals": asdict(signals),
            "reasons": list(decision.reasons),
            "effect_applied": False,
        },
        trace_id=observation.event.trace_id or observation.event.id,
        related_entity_ids=observation.event.related_entity_ids,
        goal_id=observation.event.goal_id,
    )
    append_event(database_path, event)
    return AttentionAssessment(
        observation=observation,
        decision=decision,
        event=event,
    )


def open_attention_item(
    database_path: Path,
    *,
    attention_event_id: str,
) -> AttentionItemOpening:
    """Materializa um ATTEND persistente sem alterar foco, Goal ou World."""
    assessment = get_event(database_path, attention_event_id)
    if assessment is None:
        raise ValueError(f"attention assessment não encontrado: {attention_event_id}")
    if assessment.kind != "attention.assessed":
        raise ValueError(
            f"event não é um attention assessment: {attention_event_id} ({assessment.kind})"
        )
    if assessment.payload.get("destination") != "ATTEND":
        raise ValueError("attention item exige assessment com destino ATTEND")
    if assessment.payload.get("effect_applied") is not False:
        raise ValueError("attention assessment não está disponível para materialização")

    existing = _find_attention_item_for_assessment(database_path, attention_event_id)
    if existing is not None:
        return AttentionItemOpening(item=existing, created=False)

    observation_event_id = assessment.payload.get("observation_event_id")
    if not isinstance(observation_event_id, str):
        raise TypeError(
            f"observation_event_id inválido no assessment: {attention_event_id}"
        )
    observation = get_observation(database_path, observation_event_id)
    if observation is None:
        raise ValueError(f"observation não encontrada: {observation_event_id}")

    reasons = _string_tuple_payload(assessment.payload, "reasons")
    event = Event.create(
        kind="attention.item.opened",
        source="attention",
        payload={
            "assessment_event_id": assessment.id,
            "observation_event_id": observation.event.id,
            "summary": observation.summary,
            "reasons": list(reasons),
            "status": "PENDING",
            "focus_changed": False,
            "goal_created": False,
            "effect_applied": True,
        },
        trace_id=assessment.trace_id or observation.event.trace_id or observation.event.id,
        related_entity_ids=assessment.related_entity_ids,
        goal_id=assessment.goal_id,
    )
    append_event(database_path, event)
    return AttentionItemOpening(
        item=_attention_item_from_event(event),
        created=True,
    )


def get_attention_item(database_path: Path, event_id: str) -> AttentionItem | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    return _attention_item_from_event(event)


def list_pending_attention_items(database_path: Path) -> tuple[AttentionItem, ...]:
    """Lista itens ATTEND materializados ainda pendentes em ordem de chegada."""
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'attention.item.opened'
            ORDER BY occurred_at, rowid
            """
        ).fetchall()

    items: list[AttentionItem] = []
    for row in rows:
        item = get_attention_item(database_path, str(row[0]))
        if item is not None and item.event.payload.get("status") == "PENDING":
            items.append(item)
    return tuple(items)


def _find_attention_item_for_assessment(
    database_path: Path,
    attention_event_id: str,
) -> AttentionItem | None:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'attention.item.opened'
            ORDER BY occurred_at, rowid
            """
        ).fetchall()

    for row in rows:
        item = get_attention_item(database_path, str(row[0]))
        if item is not None and item.assessment_event_id == attention_event_id:
            return item
    return None


def _attention_item_from_event(event: Event) -> AttentionItem:
    if event.kind != "attention.item.opened":
        raise ValueError(f"event não é um attention item: {event.id} ({event.kind})")

    assessment_event_id = event.payload.get("assessment_event_id")
    observation_event_id = event.payload.get("observation_event_id")
    summary = event.payload.get("summary")
    if not isinstance(assessment_event_id, str):
        raise TypeError(f"assessment_event_id inválido no attention item: {event.id}")
    if not isinstance(observation_event_id, str):
        raise TypeError(f"observation_event_id inválido no attention item: {event.id}")
    if not isinstance(summary, str) or not summary.strip():
        raise TypeError(f"summary inválido no attention item: {event.id}")

    return AttentionItem(
        event=event,
        assessment_event_id=assessment_event_id,
        observation_event_id=observation_event_id,
        summary=summary,
        reasons=_string_tuple_payload(event.payload, "reasons"),
    )


def _string_tuple_payload(payload: dict[str, object], field: str) -> tuple[str, ...]:
    raw = payload.get(field)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise TypeError(f"payload sem {field} válido")
    return tuple(item for item in raw if isinstance(item, str))
