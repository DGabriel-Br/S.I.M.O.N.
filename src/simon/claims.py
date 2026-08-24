import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from simon.entities import get_entity
from simon.events import Event, append_event, get_event
from simon.perception import get_observation
from simon.world import advance_world_revision_in_connection

ACTIVE = "ACTIVE"
TERMINAL_STATUSES = {"SUPERSEDED", "RETRACTED", "EXPIRED"}
PROPOSED_CLAIM_EVENT_KIND = "world.claim.proposed"


@dataclass(frozen=True, slots=True)
class ProposedClaim:
    event: Event
    attention_event_id: str
    observation_event_id: str
    subject_id: str
    predicate: str
    value: object
    epistemic_status: str
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    subject_id: str
    predicate: str
    value: object
    epistemic_status: str
    valid_from: datetime | None
    valid_until: datetime | None
    learned_at: datetime
    evidence_event_ids: tuple[str, ...]
    status: str

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        predicate: str,
        value: object,
        epistemic_status: str,
        evidence_event_ids: tuple[str, ...] = (),
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> Claim:
        return cls(
            id=f"clm_{uuid4().hex}",
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            epistemic_status=epistemic_status,
            valid_from=valid_from,
            valid_until=valid_until,
            learned_at=datetime.now(UTC),
            evidence_event_ids=evidence_event_ids,
            status=ACTIVE,
        )


def propose_claim_from_attention(
    database_path: Path,
    *,
    attention_event_id: str,
    subject_id: str,
    predicate: str,
    value: object,
) -> ProposedClaim:
    """Cria uma Proposed Claim sem alterar o Belief Store nem a revisão do World."""
    normalized_subject_id = subject_id.strip()
    normalized_predicate = predicate.strip()
    if not normalized_subject_id:
        raise ValueError("proposed claim exige subject_id")
    if not normalized_predicate:
        raise ValueError("proposed claim exige predicate")
    if get_entity(database_path, normalized_subject_id) is None:
        raise ValueError(f"subject da proposed claim não encontrado: {normalized_subject_id}")

    attention_event = get_event(database_path, attention_event_id)
    if attention_event is None:
        raise ValueError(f"attention assessment não encontrado: {attention_event_id}")
    if attention_event.kind != "attention.assessed":
        raise ValueError(
            f"event não é um attention assessment: {attention_event_id} "
            f"({attention_event.kind})"
        )

    destination = attention_event.payload.get("destination")
    if destination != "UPDATE_WORLD":
        raise ValueError(
            "proposed claim exige attention assessment com destino UPDATE_WORLD"
        )
    effect_applied = attention_event.payload.get("effect_applied")
    if effect_applied is not False:
        raise ValueError("attention assessment não está disponível para proposed claim")

    observation_event_id = attention_event.payload.get("observation_event_id")
    if not isinstance(observation_event_id, str):
        raise TypeError(f"observation_event_id inválido no assessment: {attention_event_id}")
    observation = get_observation(database_path, observation_event_id)
    if observation is None:
        raise ValueError(f"observation não encontrada: {observation_event_id}")
    if normalized_subject_id not in observation.event.related_entity_ids:
        raise ValueError(
            "subject da proposed claim precisa estar relacionado à observation de origem"
        )

    # O mesmo contrato JSON do Belief Store deve valer antes de uma proposta avançar.
    json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    evidence_event_ids = (observation.event.id, attention_event.id)
    epistemic_status = "DIRECT_OBSERVATION"
    event = Event.create(
        kind=PROPOSED_CLAIM_EVENT_KIND,
        source="perception",
        payload={
            "attention_event_id": attention_event.id,
            "observation_event_id": observation.event.id,
            "subject_id": normalized_subject_id,
            "predicate": normalized_predicate,
            "value": value,
            "epistemic_status": epistemic_status,
            "evidence_event_ids": list(evidence_event_ids),
            "status": "PROPOSED",
            "effect_applied": False,
        },
        trace_id=attention_event.trace_id or observation.event.trace_id or observation.event.id,
        related_entity_ids=observation.event.related_entity_ids,
        goal_id=attention_event.goal_id,
    )
    append_event(database_path, event)
    return ProposedClaim(
        event=event,
        attention_event_id=attention_event.id,
        observation_event_id=observation.event.id,
        subject_id=normalized_subject_id,
        predicate=normalized_predicate,
        value=value,
        epistemic_status=epistemic_status,
        evidence_event_ids=evidence_event_ids,
    )


def get_proposed_claim(database_path: Path, event_id: str) -> ProposedClaim | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    if event.kind != PROPOSED_CLAIM_EVENT_KIND:
        raise ValueError(f"event não é uma proposed claim: {event_id} ({event.kind})")

    attention_event_id = event.payload.get("attention_event_id")
    observation_event_id = event.payload.get("observation_event_id")
    subject_id = event.payload.get("subject_id")
    predicate = event.payload.get("predicate")
    epistemic_status = event.payload.get("epistemic_status")
    raw_evidence_event_ids = event.payload.get("evidence_event_ids")
    if not isinstance(attention_event_id, str):
        raise TypeError(f"attention_event_id inválido na proposed claim: {event_id}")
    if not isinstance(observation_event_id, str):
        raise TypeError(f"observation_event_id inválido na proposed claim: {event_id}")
    if not isinstance(subject_id, str):
        raise TypeError(f"subject_id inválido na proposed claim: {event_id}")
    if not isinstance(predicate, str):
        raise TypeError(f"predicate inválido na proposed claim: {event_id}")
    if not isinstance(epistemic_status, str):
        raise TypeError(f"epistemic_status inválido na proposed claim: {event_id}")
    if not isinstance(raw_evidence_event_ids, list) or not all(
        isinstance(item, str) for item in raw_evidence_event_ids
    ):
        raise TypeError(f"evidence_event_ids inválido na proposed claim: {event_id}")

    return ProposedClaim(
        event=event,
        attention_event_id=attention_event_id,
        observation_event_id=observation_event_id,
        subject_id=subject_id,
        predicate=predicate,
        value=event.payload.get("value"),
        epistemic_status=epistemic_status,
        evidence_event_ids=tuple(raw_evidence_event_ids),
    )


def _claim_from_row(row: tuple[object, ...]) -> Claim:
    return Claim(
        id=str(row[0]),
        subject_id=str(row[1]),
        predicate=str(row[2]),
        value=json.loads(str(row[3])),
        epistemic_status=str(row[4]),
        valid_from=datetime.fromisoformat(str(row[5])) if row[5] is not None else None,
        valid_until=datetime.fromisoformat(str(row[6])) if row[6] is not None else None,
        learned_at=datetime.fromisoformat(str(row[7])),
        evidence_event_ids=tuple(json.loads(str(row[8]))),
        status=str(row[9]),
    )


def _claim_select() -> str:
    return """
        SELECT
            id,
            subject_id,
            predicate,
            value_json,
            epistemic_status,
            valid_from,
            valid_until,
            learned_at,
            evidence_event_ids_json,
            status
        FROM claims
    """


def _insert_claim_in_connection(connection: sqlite3.Connection, claim: Claim) -> None:
    connection.execute(
        """
        INSERT INTO claims (
            id,
            subject_id,
            predicate,
            value_json,
            epistemic_status,
            valid_from,
            valid_until,
            learned_at,
            evidence_event_ids_json,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim.id,
            claim.subject_id,
            claim.predicate,
            json.dumps(claim.value, ensure_ascii=False, separators=(",", ":")),
            claim.epistemic_status,
            claim.valid_from.isoformat() if claim.valid_from is not None else None,
            claim.valid_until.isoformat() if claim.valid_until is not None else None,
            claim.learned_at.isoformat(),
            json.dumps(claim.evidence_event_ids, separators=(",", ":")),
            claim.status,
        ),
    )


def insert_claim(database_path: Path, claim: Claim) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _insert_claim_in_connection(connection, claim)
        if claim.status == ACTIVE:
            advance_world_revision_in_connection(connection)


def get_claim(database_path: Path, claim_id: str) -> Claim | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(_claim_select() + " WHERE id = ?", (claim_id,)).fetchone()
    return _claim_from_row(row) if row is not None else None


def list_active_claims(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
) -> tuple[Claim, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
    return tuple(_claim_from_row(row) for row in rows)


def list_active_claims_for_subject(
    database_path: Path,
    *,
    subject_id: str,
    limit: int = 20,
) -> tuple[Claim, ...]:
    if limit <= 0:
        raise ValueError("limit de claims precisa ser positivo")

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at DESC, id DESC LIMIT ?",
            (subject_id, limit),
        ).fetchall()
    return tuple(_claim_from_row(row) for row in rows)


def transition_claim(database_path: Path, claim_id: str, new_status: str) -> Claim:
    if new_status not in TERMINAL_STATUSES:
        raise ValueError(f"status terminal inválido: {new_status}")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE claims
            SET status = ?
            WHERE id = ? AND status = 'ACTIVE'
            """,
            (new_status, claim_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"claim não está ACTIVE: {claim_id}")
        advance_world_revision_in_connection(connection)
        row = connection.execute(_claim_select() + " WHERE id = ?", (claim_id,)).fetchone()

    if row is None:
        raise RuntimeError(f"claim desapareceu após atualização: {claim_id}")
    return _claim_from_row(row)


def set_current_claim(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
    value: object,
    epistemic_status: str,
    evidence_event_ids: tuple[str, ...] = (),
    valid_from: datetime | None = None,
) -> Claim:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
        active_claims = tuple(_claim_from_row(row) for row in rows)

        for claim in active_claims:
            if claim.value == value and claim.epistemic_status == epistemic_status:
                return claim

        if active_claims:
            connection.execute(
                """
                UPDATE claims
                SET status = 'SUPERSEDED'
                WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE'
                """,
                (subject_id, predicate),
            )

        new_claim = Claim.create(
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            epistemic_status=epistemic_status,
            evidence_event_ids=evidence_event_ids,
            valid_from=valid_from,
        )
        _insert_claim_in_connection(connection, new_claim)
        advance_world_revision_in_connection(connection)
        return new_claim
