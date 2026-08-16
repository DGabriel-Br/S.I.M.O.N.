import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    ) -> Entity:
        return cls(
            id=entity_id or f"ent_{uuid4().hex}",
            kind=kind,
            name=name,
            aliases=aliases,
            created_at=datetime.now(UTC),
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


def _entity_from_row(row: tuple[object, ...]) -> Entity:
    return Entity(
        id=str(row[0]),
        kind=str(row[1]),
        name=str(row[2]),
        aliases=tuple(json.loads(str(row[3]))),
        created_at=datetime.fromisoformat(str(row[4])),
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

    return _entity_from_row(row) if row is not None else None


def find_entities_mentioned_in_text(
    database_path: Path,
    *,
    text: str,
    limit: int = 10,
) -> tuple[Entity, ...]:
    if limit <= 0:
        raise ValueError("limit de entities precisa ser positivo")

    normalized_text = text.strip().casefold()
    if not normalized_text:
        return ()

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                kind,
                name,
                aliases_json,
                created_at
            FROM entities
            ORDER BY created_at, id
            """
        ).fetchall()

    matches: list[Entity] = []
    for row in rows:
        entity = _entity_from_row(row)
        terms = (entity.name, *entity.aliases)
        if any(_contains_term(normalized_text, term) for term in terms):
            matches.append(entity)
            if len(matches) == limit:
                break

    return tuple(matches)


def _contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = term.strip().casefold()
    if not normalized_term:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_term)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


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
