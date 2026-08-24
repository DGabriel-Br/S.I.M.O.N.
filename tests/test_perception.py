from pathlib import Path

import pytest

from simon.entities import Entity, insert_entity
from simon.events import get_event
from simon.goals import Goal, insert_goal
from simon.perception import get_observation, record_observation
from simon.storage import initialize_storage
from simon.world import get_world_revision


def test_observation_survives_new_database_connection_without_changing_world(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    before_revision = get_world_revision(database_path)

    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="target.txt foi alterado",
        details={"path": "target.txt"},
        trace_id="trace_observation",
    )

    restored = get_observation(database_path, observation.event.id)
    assert restored == observation
    assert get_world_revision(database_path) == before_revision


def test_observation_preserves_explicit_goal_and_entity_provenance(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Acompanhar projeto",
        origin="USER",
        desired_state={"status": "healthy"},
        success_criteria=({"kind": "healthy"},),
    )
    insert_goal(database_path, goal)
    entity = Entity.create(kind="file", name="target.txt")
    insert_entity(database_path, entity)

    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="target.txt mudou",
        goal_id=goal.id,
        related_entity_ids=(entity.id,),
    )

    event = get_event(database_path, observation.event.id)
    assert event is not None
    assert event.goal_id == goal.id
    assert event.related_entity_ids == (entity.id,)


def test_observation_rejects_dangling_goal_or_entity(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    with pytest.raises(ValueError, match="goal relacionado"):
        record_observation(
            database_path,
            observer="filesystem",
            signal_kind="file.changed",
            summary="mudança",
            goal_id="gol_missing",
        )

    with pytest.raises(ValueError, match="entity relacionada"):
        record_observation(
            database_path,
            observer="filesystem",
            signal_kind="file.changed",
            summary="mudança",
            related_entity_ids=("ent_missing",),
        )
