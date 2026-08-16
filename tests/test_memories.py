from pathlib import Path

import pytest

from simon.claims import Claim, insert_claim
from simon.entities import Entity, insert_entity
from simon.experiences import close_experience, create_experience
from simon.memories import create_memory, get_memory, retrieve_memories, transition_memory
from simon.storage import initialize_storage


def _closed_experience(database_path: Path, title: str = "Experiência concluída") -> str:
    experience = create_experience(database_path, title=title)
    closed = close_experience(
        database_path,
        experience.id,
        outcome="SUCCESS",
        summary="Resultado útil confirmado.",
    )
    return closed.id


def test_memory_persists_meaning_with_provenance(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    entity = Entity.create(kind="project", name="Unlimited OCR")
    insert_entity(database_path, entity)
    claim = Claim.create(
        subject_id=entity.id,
        predicate="generation.status",
        value="resolved",
        epistemic_status="DIRECT_OBSERVATION",
    )
    insert_claim(database_path, claim)

    memory = create_memory(
        database_path,
        kind="SEMANTIC",
        content="O loop de geração foi resolvido após corrigir a condição de parada.",
        scope="PROJECT",
        source_experience_ids=(experience_id,),
        entity_ids=(entity.id,),
        source_claim_ids=(claim.id,),
    )

    restored = get_memory(database_path, memory.id)

    assert restored == memory
    assert restored is not None
    assert restored.status == "ACTIVE"
    assert restored.source_experience_ids == (experience_id,)
    assert restored.entity_ids == (entity.id,)
    assert restored.source_claim_ids == (claim.id,)


def test_memory_requires_closed_source_experience(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience = create_experience(database_path, title="Ainda em andamento")

    with pytest.raises(ValueError, match="experience fechada"):
        create_memory(
            database_path,
            kind="EPISODIC",
            content="Ainda não deveria virar memória.",
            scope="PROJECT",
            source_experience_ids=(experience.id,),
        )


def test_memory_rejects_unknown_provenance_references(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)

    with pytest.raises(ValueError, match="entity da memory não encontrada"):
        create_memory(
            database_path,
            kind="SEMANTIC",
            content="Conhecimento com entidade inexistente.",
            scope="PROJECT",
            source_experience_ids=(experience_id,),
            entity_ids=("ent_missing",),
        )

    with pytest.raises(ValueError, match="claim de origem não encontrada"):
        create_memory(
            database_path,
            kind="SEMANTIC",
            content="Conhecimento com claim inexistente.",
            scope="PROJECT",
            source_experience_ids=(experience_id,),
            source_claim_ids=("clm_missing",),
        )


def test_retrieval_filters_active_memories_and_records_use(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    entity = Entity.create(kind="project", name="Unlimited OCR")
    insert_entity(database_path, entity)

    expected = create_memory(
        database_path,
        kind="SEMANTIC",
        content="Generation loop exigiu validar a condição de parada do decoder.",
        scope="PROJECT",
        source_experience_ids=(experience_id,),
        entity_ids=(entity.id,),
    )
    create_memory(
        database_path,
        kind="EPISODIC",
        content="Outro resultado sem relação com o decoder.",
        scope="GLOBAL",
        source_experience_ids=(experience_id,),
    )

    retrieved = retrieve_memories(
        database_path,
        query="GENERATION LOOP",
        kinds=("SEMANTIC",),
        scopes=("PROJECT",),
        entity_id=entity.id,
        limit=5,
    )

    assert tuple(memory.id for memory in retrieved) == (expected.id,)
    assert retrieved[0].last_used_at is not None
    stored = get_memory(database_path, expected.id)
    assert stored is not None
    assert stored.last_used_at == retrieved[0].last_used_at


def test_archived_memory_leaves_normal_retrieval(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    memory = create_memory(
        database_path,
        kind="EPISODIC",
        content="Tentativa antiga que não deve aparecer no retrieval normal.",
        scope="GLOBAL",
        source_experience_ids=(experience_id,),
    )

    archived = transition_memory(database_path, memory.id, "ARCHIVED")
    retrieved = retrieve_memories(database_path, query="tentativa antiga")

    assert archived.status == "ARCHIVED"
    assert retrieved == ()


def test_terminal_memory_cannot_be_transitioned_again(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    memory = create_memory(
        database_path,
        kind="META",
        content="Uma observação sobre o próprio funcionamento do SIMON.",
        scope="SYSTEM",
        source_experience_ids=(experience_id,),
    )
    transition_memory(database_path, memory.id, "SUPERSEDED")

    with pytest.raises(ValueError, match="não está ativa"):
        transition_memory(database_path, memory.id, "RETRACTED")


def test_memory_can_consolidate_multiple_closed_experiences_without_duplicate_sources(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _closed_experience(database_path, "Primeira observação")
    second = _closed_experience(database_path, "Segunda observação")

    memory = create_memory(
        database_path,
        kind="SEMANTIC",
        content="O mesmo padrão foi observado em experiências independentes.",
        scope="GLOBAL",
        source_experience_ids=(first, second, first),
    )

    assert memory.source_experience_ids == (first, second)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", "UNKNOWN", "kind de memory inválido"),
        ("scope", "EVERYWHERE", "scope de memory inválido"),
        ("content", "   ", "memory precisa de conteúdo"),
    ],
)
def test_memory_rejects_invalid_basic_fields(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience_id = _closed_experience(database_path)
    arguments = {
        "kind": "EPISODIC",
        "content": "Conteúdo válido",
        "scope": "GLOBAL",
        "source_experience_ids": (experience_id,),
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=message):
        create_memory(database_path, **arguments)  # type: ignore[arg-type]
