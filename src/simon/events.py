import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    kind: str
    occurred_at: datetime
    source: str
    payload: dict[str, object]
    trace_id: str | None = None
    related_entity_ids: tuple[str, ...] = field(default_factory=tuple)
    goal_id: str | None = None
    experience_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        source: str,
        payload: dict[str, object] | None = None,
        trace_id: str | None = None,
        related_entity_ids: tuple[str, ...] = (),
        goal_id: str | None = None,
        experience_id: str | None = None,
    ) -> Event:
        return cls(
            id=f"evt_{uuid4().hex}",
            kind=kind,
            occurred_at=datetime.now(UTC),
            source=source,
            payload=payload or {},
            trace_id=trace_id,
            related_entity_ids=related_entity_ids,
            goal_id=goal_id,
            experience_id=experience_id,
        )


def append_event(database_path: Path, event: Event) -> None:
    payload_json = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    related_entity_ids_json = json.dumps(event.related_entity_ids, separators=(",", ":"))

    with sqlite3.connect(database_path) as connection:
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
                payload_json,
                event.trace_id,
                related_entity_ids_json,
                event.goal_id,
                event.experience_id,
            ),
        )


def get_event(database_path: Path, event_id: str) -> Event | None:
    with sqlite3.connect(database_path) as connection:
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
        return None

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
