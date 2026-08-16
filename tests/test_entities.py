from pathlib import Path

from simon.entities import Entity, get_entity, get_or_create_entity, insert_entity
from simon.storage import initialize_storage


def test_entity_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    entity = Entity.create(
        kind="project",
        name="SIMON",
        aliases=("S.I.M.O.N.",),
    )

    insert_entity(database_path, entity)
    restored = get_entity(database_path, entity.id)

    assert restored == entity


def test_get_or_create_entity_keeps_stable_identity(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    first = get_or_create_entity(
        database_path,
        entity_id="ent_known_project",
        kind="project",
        name="Known Project",
    )
    second = get_or_create_entity(
        database_path,
        entity_id="ent_known_project",
        kind="project",
        name="Known Project",
    )

    assert second == first
