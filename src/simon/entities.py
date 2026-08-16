from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


SIMON_ENTITY_ID = "ent_simon"


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    kind: str
    name: str
    aliases: tuple[str, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        name: str,
        aliases: tuple[str, ...] = (),
        entity_id: str | None = None,
    ) -> "Entity":
        return cls(
            id=entity_id or f"ent_{uuid4().hex}",
            kind=kind,
            name=name,
            aliases=aliases,
            created_at=datetime.now(timezone.utc),
        )


def insert_entity(database_path: Path, entity: Entity) -> None:
    aliases_json = json.dumps(entity.aliases, ensure_ascii=False, separators=(",", ":"))

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO entities (
                id,
                kind,
                name,
                aliases_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                entity.id,
                entity.kind,
                entity.name,
                aliases_json,
                entity.created_at.isoformat(),
            ),
        )


def get_entity(database_path: Path, entity_id: str) -> Entity | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                kind,
                name,
                aliases_json,
                created_at
            FROM entities
            WHERE id = ?
            """,
            (entity_id,),
        ).fetchone()

    if row is None:
        return None

    return Entity(
        id=str(row[0]),
        kind=str(row[1]),
        name=str(row[2]),
        aliases=tuple(json.loads(str(row[3]))),
        created_at=datetime.fromisoformat(str(row[4])),
    )


def get_or_create_entity(
    database_path: Path,
    *,
    entity_id: str,
    kind: str,
    name: str,
    aliases: tuple[str, ...] = (),
) -> Entity:
    existing = get_entity(database_path, entity_id)
    if existing is not None:
        return existing

    entity = Entity.create(
        entity_id=entity_id,
        kind=kind,
        name=name,
        aliases=aliases,
    )
    insert_entity(database_path, entity)
    return entity
