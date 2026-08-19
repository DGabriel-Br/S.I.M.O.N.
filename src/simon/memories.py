import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

KINDS = {"EPISODIC", "SEMANTIC", "PROCEDURAL", "META"}
SCOPES = {"GLOBAL", "PROJECT", "WORKSPACE", "SESSION", "PRIVATE", "SYSTEM", "LAB"}
TERMINAL_STATUSES = {"ARCHIVED", "SUPERSEDED", "RETRACTED"}


@dataclass(frozen=True, slots=True)
class Memory:
    id: str
    kind: str
    content: str
    scope: str
    entity_ids: tuple[str, ...]
    source_experience_ids: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    status: str
    created_at: datetime
    last_used_at: datetime | None


def _memory_from_row(row: tuple[object, ...]) -> Memory:
    return Memory(
        id=str(row[0]),
        kind=str(row[1]),
        content=str(row[2]),
        scope=str(row[3]),
        entity_ids=tuple(json.loads(str(row[4]))),
        source_experience_ids=tuple(json.loads(str(row[5]))),
        source_claim_ids=tuple(json.loads(str(row[6]))),
        status=str(row[7]),
        created_at=datetime.fromisoformat(str(row[8])),
        last_used_at=datetime.fromisoformat(str(row[9])) if row[9] is not None else None,
    )


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _validate_references(
    connection: sqlite3.Connection,
    *,
    experience_ids: tuple[str, ...],
    entity_ids: tuple[str, ...],
    claim_ids: tuple[str, ...],
) -> None:
    if not experience_ids:
        raise ValueError("memory precisa de ao menos uma experience de origem")

    for experience_id in experience_ids:
        row = connection.execute(
            "SELECT status FROM experiences WHERE id = ?",
            (experience_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"experience de origem não encontrada: {experience_id}")
        if str(row[0]) != "CLOSED":
            raise ValueError(f"memory exige experience fechada: {experience_id}")

    for entity_id in entity_ids:
        row = connection.execute(
            "SELECT id FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"entity da memory não encontrada: {entity_id}")

    for claim_id in claim_ids:
        row = connection.execute(
            "SELECT id FROM claims WHERE id = ?",
            (claim_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"claim de origem não encontrada: {claim_id}")


def create_memory_in_connection(
    connection: sqlite3.Connection,
    *,
    kind: str,
    content: str,
    scope: str,
    source_experience_ids: tuple[str, ...],
    entity_ids: tuple[str, ...] = (),
    source_claim_ids: tuple[str, ...] = (),
) -> Memory:
    if kind not in KINDS:
        raise ValueError(f"kind de memory inválido: {kind}")
    if scope not in SCOPES:
        raise ValueError(f"scope de memory inválido: {scope}")

    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("memory precisa de conteúdo")

    normalized_experience_ids = _unique(source_experience_ids)
    normalized_entity_ids = _unique(entity_ids)
    normalized_claim_ids = _unique(source_claim_ids)
    now = datetime.now(UTC)
    memory = Memory(
        id=f"mem_{uuid4().hex}",
        kind=kind,
        content=normalized_content,
        scope=scope,
        entity_ids=normalized_entity_ids,
        source_experience_ids=normalized_experience_ids,
        source_claim_ids=normalized_claim_ids,
        status="ACTIVE",
        created_at=now,
        last_used_at=None,
    )

    _validate_references(
        connection,
        experience_ids=memory.source_experience_ids,
        entity_ids=memory.entity_ids,
        claim_ids=memory.source_claim_ids,
    )
    connection.execute(
        """
        INSERT INTO memories (
            id,
            kind,
            content,
            scope,
            entity_ids_json,
            source_experience_ids_json,
            source_claim_ids_json,
            status,
            created_at,
            last_used_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memory.id,
            memory.kind,
            memory.content,
            memory.scope,
            json.dumps(memory.entity_ids, separators=(",", ":")),
            json.dumps(memory.source_experience_ids, separators=(",", ":")),
            json.dumps(memory.source_claim_ids, separators=(",", ":")),
            memory.status,
            memory.created_at.isoformat(),
            None,
        ),
    )
    return memory


def create_memory(
    database_path: Path,
    *,
    kind: str,
    content: str,
    scope: str,
    source_experience_ids: tuple[str, ...],
    entity_ids: tuple[str, ...] = (),
    source_claim_ids: tuple[str, ...] = (),
) -> Memory:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return create_memory_in_connection(
            connection,
            kind=kind,
            content=content,
            scope=scope,
            source_experience_ids=source_experience_ids,
            entity_ids=entity_ids,
            source_claim_ids=source_claim_ids,
        )


def get_memory(database_path: Path, memory_id: str) -> Memory | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                kind,
                content,
                scope,
                entity_ids_json,
                source_experience_ids_json,
                source_claim_ids_json,
                status,
                created_at,
                last_used_at
            FROM memories
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()

    return _memory_from_row(row) if row is not None else None


def transition_memory(database_path: Path, memory_id: str, new_status: str) -> Memory:
    if new_status not in TERMINAL_STATUSES:
        raise ValueError(f"estado de memory inválido: {new_status}")

    current = get_memory(database_path, memory_id)
    if current is None:
        raise ValueError(f"memory não encontrada: {memory_id}")
    if current.status != "ACTIVE":
        raise ValueError(f"memory não está ativa: {memory_id}")

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "UPDATE memories SET status = ? WHERE id = ? AND status = 'ACTIVE'",
            (new_status, memory_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"memory mudou durante a transição: {memory_id}")

    updated = get_memory(database_path, memory_id)
    if updated is None:
        raise RuntimeError(f"memory desapareceu após atualização: {memory_id}")
    return updated


def retrieve_memories(
    database_path: Path,
    *,
    query: str | None = None,
    kinds: tuple[str, ...] = (),
    scopes: tuple[str, ...] = (),
    entity_id: str | None = None,
    limit: int = 10,
) -> tuple[Memory, ...]:
    if limit <= 0:
        raise ValueError("limit de retrieval precisa ser positivo")
    invalid_kinds = set(kinds) - KINDS
    if invalid_kinds:
        raise ValueError(f"kind de retrieval inválido: {min(invalid_kinds)}")
    invalid_scopes = set(scopes) - SCOPES
    if invalid_scopes:
        raise ValueError(f"scope de retrieval inválido: {min(invalid_scopes)}")

    normalized_query = query.strip().casefold() if query is not None else ""
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                kind,
                content,
                scope,
                entity_ids_json,
                source_experience_ids_json,
                source_claim_ids_json,
                status,
                created_at,
                last_used_at
            FROM memories
            WHERE status = 'ACTIVE'
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

        candidates = (_memory_from_row(row) for row in rows)
        selected: list[Memory] = []
        for memory in candidates:
            if kinds and memory.kind not in kinds:
                continue
            if scopes and memory.scope not in scopes:
                continue
            if entity_id is not None and entity_id not in memory.entity_ids:
                continue
            if normalized_query and normalized_query not in memory.content.casefold():
                continue

            selected.append(memory)
            if len(selected) == limit:
                break

        if not selected:
            return ()

        used_at = datetime.now(UTC)
        connection.executemany(
            "UPDATE memories SET last_used_at = ? WHERE id = ? AND status = 'ACTIVE'",
            ((used_at.isoformat(), memory.id) for memory in selected),
        )

    return tuple(replace(memory, last_used_at=used_at) for memory in selected)
