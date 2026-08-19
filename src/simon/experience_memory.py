from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from simon.events import Event
from simon.experiences import Experience
from simon.memories import Memory, create_memory_in_connection

PROMOTION_EVENT_KIND = "memory.promoted_from_experience"


@dataclass(frozen=True, slots=True)
class ExperienceMemoryReceipt:
    experience: Experience
    memory: Memory
    promotion_event_id: str


def promote_experience_to_memory(
    database_path: Path,
    *,
    experience_id: str,
    kind: str,
    content: str,
    scope: str,
    entity_ids: tuple[str, ...] = (),
    source_claim_ids: tuple[str, ...] = (),
    trace_id: str | None = None,
) -> ExperienceMemoryReceipt:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        experience = _get_experience_in_connection(connection, experience_id)
        if experience is None:
            raise ValueError(f"experience não encontrada: {experience_id}")
        if experience.status != "CLOSED":
            raise ValueError("promoção de Memory exige Experience CLOSED")

        memory = create_memory_in_connection(
            connection,
            kind=kind,
            content=content,
            scope=scope,
            source_experience_ids=(experience.id,),
            entity_ids=entity_ids,
            source_claim_ids=source_claim_ids,
        )
        promotion_event = Event.create(
            kind=PROMOTION_EVENT_KIND,
            source="user",
            payload={
                "memory_id": memory.id,
                "experience_id": experience.id,
                "kind": memory.kind,
                "scope": memory.scope,
                "content_sha256": hashlib.sha256(memory.content.encode("utf-8")).hexdigest(),
                "source_claim_ids": list(memory.source_claim_ids),
            },
            trace_id=trace_id or f"trc_{uuid4().hex}",
            related_entity_ids=memory.entity_ids,
            goal_id=experience.goal_id,
            experience_id=experience.id,
        )
        _insert_event(connection, promotion_event)

    return ExperienceMemoryReceipt(
        experience=experience,
        memory=memory,
        promotion_event_id=promotion_event.id,
    )


def _get_experience_in_connection(
    connection: sqlite3.Connection,
    experience_id: str,
) -> Experience | None:
    row = connection.execute(
        """
        SELECT
            id,
            title,
            goal_id,
            parent_experience_id,
            status,
            outcome,
            event_ids_json,
            action_ids_json,
            verification_ids_json,
            summary,
            started_at,
            ended_at,
            updated_at
        FROM experiences
        WHERE id = ?
        """,
        (experience_id,),
    ).fetchone()
    if row is None:
        return None
    return Experience(
        id=str(row[0]),
        title=str(row[1]),
        goal_id=str(row[2]) if row[2] is not None else None,
        parent_experience_id=str(row[3]) if row[3] is not None else None,
        status=str(row[4]),
        outcome=str(row[5]) if row[5] is not None else None,
        event_ids=tuple(json.loads(str(row[6]))),
        action_ids=tuple(json.loads(str(row[7]))),
        verification_ids=tuple(json.loads(str(row[8]))),
        summary=str(row[9]) if row[9] is not None else None,
        started_at=datetime.fromisoformat(str(row[10])),
        ended_at=(
            datetime.fromisoformat(str(row[11]))
            if row[11] is not None
            else None
        ),
        updated_at=datetime.fromisoformat(str(row[12])),
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
