import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from simon.claims import Claim, insert_claim
from simon.entities import Entity, insert_entity
from simon.experience_memory import promote_experience_to_memory
from simon.experiences import close_experience, create_experience
from simon.memories import get_memory, retrieve_memories
from simon.storage import initialize_storage


def _closed_experience(database_path: Path, *, outcome: str = "SUCCESS") -> str:
    experience = create_experience(database_path, title="Corrigir execução")
    return close_experience(
        database_path,
        experience.id,
        outcome=outcome,
        summary="O ciclo produziu uma conclusão útil.",
    ).id


def test_explicit_promotion_creates_memory_with_experience_provenance(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)

    receipt = promote_experience_to_memory(
        database_path,
        experience_id=experience_id,
        kind="SEMANTIC",
        scope="PROJECT",
        content="Validar o resultado observado antes de concluir que uma correção funcionou.",
    )

    restored = get_memory(database_path, receipt.memory.id)
    assert restored == receipt.memory
    assert receipt.memory.source_experience_ids == (experience_id,)
    assert receipt.memory.status == "ACTIVE"

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT source, payload_json, experience_id, goal_id
            FROM events
            WHERE id = ?
            """,
            (receipt.promotion_event_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "user"
    payload = json.loads(str(row[1]))
    assert payload["memory_id"] == receipt.memory.id
    assert payload["experience_id"] == experience_id
    assert payload["content_sha256"] == hashlib.sha256(
        receipt.memory.content.encode("utf-8")
    ).hexdigest()
    assert row[2] == experience_id
    assert row[3] is None


def test_promotion_accepts_failure_as_negative_knowledge(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path, outcome="FAILURE")

    receipt = promote_experience_to_memory(
        database_path,
        experience_id=experience_id,
        kind="EPISODIC",
        scope="PROJECT",
        content="A estratégia falhou porque a condição observada não sustentava a hipótese.",
    )

    assert receipt.experience.outcome == "FAILURE"
    assert receipt.memory.kind == "EPISODIC"


def test_promotion_rejects_open_experience_without_creating_memory(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience = create_experience(database_path, title="Ainda aberta")

    with pytest.raises(ValueError, match="Experience CLOSED"):
        promote_experience_to_memory(
            database_path,
            experience_id=experience.id,
            kind="SEMANTIC",
            scope="PROJECT",
            content="Não deve ser persistido.",
        )

    with sqlite3.connect(database_path) as connection:
        memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'memory.promoted_from_experience'"
        ).fetchone()

    assert memory_count == (0,)
    assert event_count == (0,)


def test_promotion_validates_entity_and_claim_references_atomically(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    entity = Entity.create(kind="project", name="SIMON")
    insert_entity(database_path, entity)
    claim = Claim.create(
        subject_id=entity.id,
        predicate="test.status",
        value="verified",
        epistemic_status="DIRECT_OBSERVATION",
    )
    insert_claim(database_path, claim)

    receipt = promote_experience_to_memory(
        database_path,
        experience_id=experience_id,
        kind="SEMANTIC",
        scope="PROJECT",
        content="Uma conclusão sustentada por evidência persistida.",
        entity_ids=(entity.id,),
        source_claim_ids=(claim.id,),
    )
    assert receipt.memory.entity_ids == (entity.id,)
    assert receipt.memory.source_claim_ids == (claim.id,)

    with pytest.raises(ValueError, match="claim de origem não encontrada"):
        promote_experience_to_memory(
            database_path,
            experience_id=experience_id,
            kind="SEMANTIC",
            scope="PROJECT",
            content="Esta promoção deve falhar por proveniência inválida.",
            source_claim_ids=("clm_missing",),
        )

    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()
    assert count == (1,)


def test_promoted_memory_enters_normal_retrieval(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    receipt = promote_experience_to_memory(
        database_path,
        experience_id=experience_id,
        kind="SEMANTIC",
        scope="PROJECT",
        content="Reexecutar depois da correção evita concluir com base em estado antigo.",
    )

    retrieved = retrieve_memories(
        database_path,
        query="estado antigo",
        kinds=("SEMANTIC",),
        scopes=("PROJECT",),
    )

    assert tuple(memory.id for memory in retrieved) == (receipt.memory.id,)
    assert retrieved[0].last_used_at is not None
