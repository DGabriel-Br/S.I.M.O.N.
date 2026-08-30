from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from simon.cognition import GoalProposal
from simon.events import Event, append_event, get_event
from simon.perception import Observation, get_observation

AttentionDestination = Literal["IGNORE", "RECORD", "UPDATE_WORLD", "ATTEND", "INTERRUPT"]
AttentionReviewDecision = Literal["DISMISS", "ACKNOWLEDGE", "PROPOSE_GOAL"]
AttentionItemStatus = Literal["PENDING", "DISMISSED", "ACKNOWLEDGED", "GOAL_PROPOSED"]


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
class AttentionItemReview:
    event: Event
    attention_item_event_id: str
    decision: AttentionReviewDecision
    status: AttentionItemStatus
    goal_proposal_event_id: str | None


@dataclass(frozen=True, slots=True)
class AttentionItemReviewReceipt:
    review: AttentionItemReview
    goal_proposal_event: Event | None
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


def review_attention_item(
    database_path: Path,
    *,
    attention_item_event_id: str,
    decision: AttentionReviewDecision,
    goal_proposal: GoalProposal | None = None,
) -> AttentionItemReviewReceipt:
    """Fecha um item ATTEND por decisão humana, sem trocar foco nem criar Goal."""
    normalized_item_id = attention_item_event_id.strip()
    if not normalized_item_id:
        raise ValueError("attention_item_event_id não pode ser vazio")
    if decision == "PROPOSE_GOAL" and goal_proposal is None:
        raise ValueError("PROPOSE_GOAL exige uma proposta de Goal estruturada")
    if decision != "PROPOSE_GOAL" and goal_proposal is not None:
        raise ValueError("proposta de Goal só pode acompanhar decisão PROPOSE_GOAL")

    existing_review_id: str | None = None
    existing_goal_proposal_event_id: str | None = None
    review_event: Event | None = None
    proposal_event: Event | None = None

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        item = _load_attention_item_for_review(connection, normalized_item_id)
        existing = _find_attention_item_review_in_connection(connection, normalized_item_id)
        if existing is not None:
            existing_review_id, existing_decision, existing_goal_proposal_event_id = existing
            if existing_decision != decision:
                raise ValueError(
                    "attention item já foi revisado com decisão diferente: "
                    f"{normalized_item_id} ({existing_decision})"
                )
            if decision == "PROPOSE_GOAL":
                if existing_goal_proposal_event_id is None or goal_proposal is None:
                    raise RuntimeError(
                        "review PROPOSE_GOAL persistida sem proposta de Goal recuperável"
                    )
                existing_proposal_event = _load_event_by_id(
                    connection, existing_goal_proposal_event_id
                )
                stored_proposal = existing_proposal_event.payload.get("proposal")
                if stored_proposal != goal_proposal.model_dump(mode="json"):
                    raise ValueError(
                        "attention item já possui proposta de Goal diferente; "
                        "a review é imutável"
                    )
        else:
            status = _review_status(decision)
            if decision == "PROPOSE_GOAL":
                if goal_proposal is None:
                    raise RuntimeError("PROPOSE_GOAL sem GoalProposal após validação")
                proposal_event = Event.create(
                    kind="attention.goal_proposal.completed",
                    source="user",
                    payload={
                        "attention_item_event_id": item.event.id,
                        "assessment_event_id": item.assessment_event_id,
                        "observation_event_id": item.observation_event_id,
                        "proposal": goal_proposal.model_dump(mode="json"),
                        "model": None,
                        "origin": "ATTENTION_REVIEW",
                        "authority": "USER_DECISION",
                        "materialized_by": "attention",
                    },
                    trace_id=item.event.trace_id or item.event.id,
                    related_entity_ids=item.event.related_entity_ids,
                )

            review_event = Event.create(
                kind="attention.item.reviewed",
                source="user",
                payload={
                    "attention_item_event_id": item.event.id,
                    "assessment_event_id": item.assessment_event_id,
                    "observation_event_id": item.observation_event_id,
                    "decision": decision,
                    "status": status,
                    "goal_proposal_event_id": proposal_event.id if proposal_event else None,
                    "authority": "USER_DECISION",
                    "focus_changed": False,
                    "goal_created": False,
                    "effect_applied": True,
                },
                trace_id=item.event.trace_id or item.event.id,
                related_entity_ids=item.event.related_entity_ids,
                goal_id=item.event.goal_id,
            )
            if proposal_event is not None:
                _insert_event(connection, proposal_event)
            _insert_event(connection, review_event)

    if existing_review_id is not None:
        existing_event = get_event(database_path, existing_review_id)
        if existing_event is None:
            raise RuntimeError(
                f"review persistida não está mais disponível: {existing_review_id}"
            )
        existing_proposal = (
            get_event(database_path, existing_goal_proposal_event_id)
            if existing_goal_proposal_event_id is not None
            else None
        )
        if existing_goal_proposal_event_id is not None and existing_proposal is None:
            raise RuntimeError(
                "review referencia proposta de Goal indisponível: "
                f"{existing_goal_proposal_event_id}"
            )
        return AttentionItemReviewReceipt(
            review=_attention_review_from_event(existing_event),
            goal_proposal_event=existing_proposal,
            created=False,
        )

    if review_event is None:
        raise RuntimeError("review de Attention terminou sem criar ou recuperar Event")
    return AttentionItemReviewReceipt(
        review=_attention_review_from_event(review_event),
        goal_proposal_event=proposal_event,
        created=True,
    )


def get_attention_item_review(
    database_path: Path,
    attention_item_event_id: str,
) -> AttentionItemReview | None:
    with sqlite3.connect(database_path) as connection:
        existing = _find_attention_item_review_in_connection(
            connection,
            attention_item_event_id,
        )
    if existing is None:
        return None
    event = get_event(database_path, existing[0])
    if event is None:
        raise RuntimeError(f"review persistida não encontrada: {existing[0]}")
    return _attention_review_from_event(event)


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
        reviewed_item_ids = _reviewed_attention_item_ids(connection)

    items: list[AttentionItem] = []
    for row in rows:
        item_id = str(row[0])
        if item_id in reviewed_item_ids:
            continue
        item = get_attention_item(database_path, item_id)
        if item is not None and item.event.payload.get("status") == "PENDING":
            items.append(item)
    return tuple(items)


def _load_event_by_id(connection: sqlite3.Connection, event_id: str) -> Event:
    row = connection.execute(
        """
        SELECT
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        FROM events
        WHERE id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Event não encontrado: {event_id}")
    return _event_from_row(row)


def _load_attention_item_for_review(
    connection: sqlite3.Connection,
    attention_item_event_id: str,
) -> AttentionItem:
    row = connection.execute(
        """
        SELECT
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        FROM events
        WHERE id = ?
        """,
        (attention_item_event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"attention item não encontrado: {attention_item_event_id}")
    event = _event_from_row(row)
    item = _attention_item_from_event(event)
    if item.event.payload.get("status") != "PENDING":
        raise ValueError(f"attention item não está PENDING: {attention_item_event_id}")
    return item


def _find_attention_item_review_in_connection(
    connection: sqlite3.Connection,
    attention_item_event_id: str,
) -> tuple[str, AttentionReviewDecision, str | None] | None:
    rows = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'attention.item.reviewed'
        ORDER BY occurred_at, rowid
        """
    ).fetchall()
    for event_id, payload_json in rows:
        payload = json.loads(str(payload_json))
        if not isinstance(payload, dict):
            raise TypeError(f"payload de review inválido: {event_id}")
        if payload.get("attention_item_event_id") != attention_item_event_id:
            continue
        decision = payload.get("decision")
        if decision not in {"DISMISS", "ACKNOWLEDGE", "PROPOSE_GOAL"}:
            raise TypeError(f"decision inválida em attention review: {event_id}")
        proposal_event_id = payload.get("goal_proposal_event_id")
        if proposal_event_id is not None and not isinstance(proposal_event_id, str):
            raise TypeError(f"goal_proposal_event_id inválido em attention review: {event_id}")
        return str(event_id), cast(AttentionReviewDecision, decision), proposal_event_id
    return None


def _reviewed_attention_item_ids(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM events
        WHERE kind = 'attention.item.reviewed'
        """
    ).fetchall()
    reviewed: set[str] = set()
    for (payload_json,) in rows:
        payload = json.loads(str(payload_json))
        if not isinstance(payload, dict):
            raise TypeError("payload de attention review inválido")
        item_id = payload.get("attention_item_event_id")
        if not isinstance(item_id, str):
            raise TypeError("attention review sem attention_item_event_id válido")
        reviewed.add(item_id)
    return reviewed


def _review_status(decision: AttentionReviewDecision) -> AttentionItemStatus:
    if decision == "DISMISS":
        return "DISMISSED"
    if decision == "ACKNOWLEDGE":
        return "ACKNOWLEDGED"
    return "GOAL_PROPOSED"


def _attention_review_from_event(event: Event) -> AttentionItemReview:
    if event.kind != "attention.item.reviewed":
        raise ValueError(f"event não é attention review: {event.id} ({event.kind})")
    item_id = event.payload.get("attention_item_event_id")
    decision = event.payload.get("decision")
    status = event.payload.get("status")
    proposal_event_id = event.payload.get("goal_proposal_event_id")
    if not isinstance(item_id, str):
        raise TypeError(f"attention_item_event_id inválido em review: {event.id}")
    if decision not in {"DISMISS", "ACKNOWLEDGE", "PROPOSE_GOAL"}:
        raise TypeError(f"decision inválida em review: {event.id}")
    if status not in {"DISMISSED", "ACKNOWLEDGED", "GOAL_PROPOSED"}:
        raise TypeError(f"status inválido em review: {event.id}")
    if proposal_event_id is not None and not isinstance(proposal_event_id, str):
        raise TypeError(f"goal_proposal_event_id inválido em review: {event.id}")
    return AttentionItemReview(
        event=event,
        attention_item_event_id=item_id,
        decision=cast(AttentionReviewDecision, decision),
        status=cast(AttentionItemStatus, status),
        goal_proposal_event_id=proposal_event_id,
    )


def _event_from_row(row: tuple[object, ...]) -> Event:
    return Event(
        id=str(row[0]),
        kind=str(row[1]),
        occurred_at=datetime.fromisoformat(str(row[2])),
        source=str(row[3]),
        payload=json.loads(str(row[4])),
        trace_id=str(row[5]) if row[5] is not None else None,
        related_entity_ids=tuple(json.loads(str(row[6]))),
        goal_id=str(row[7]) if row[7] is not None else None,
        experience_id=str(row[8]) if row[8] is not None else None,
    )


def _insert_event(connection: sqlite3.Connection, event: Event) -> None:
    connection.execute(
        """
        INSERT INTO events (
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.kind,
            event.occurred_at.isoformat(),
            event.source,
            json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
            event.trace_id,
            json.dumps(event.related_entity_ids, separators=(",", ":")),
            event.goal_id,
            event.experience_id,
        ),
    )


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
