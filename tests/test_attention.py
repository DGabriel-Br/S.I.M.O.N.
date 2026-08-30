from pathlib import Path

import pytest

from simon.attention import (
    AttentionSignals,
    assess_observation_attention,
    decide_attention,
    get_attention_item,
    list_pending_attention_items,
    open_attention_item,
)
from simon.events import Event, append_event, get_event
from simon.perception import record_observation
from simon.storage import initialize_storage
from simon.world import get_world_revision


@pytest.mark.parametrize(
    ("signals", "destination"),
    [
        (AttentionSignals(), "RECORD"),
        (AttentionSignals(known_noise=True), "IGNORE"),
        (AttentionSignals(world_change=True), "UPDATE_WORLD"),
        (AttentionSignals(goal_relevant=True), "ATTEND"),
        (AttentionSignals(subscribed=True), "ATTEND"),
        (AttentionSignals(urgent=True), "INTERRUPT"),
        (AttentionSignals(risk=True), "INTERRUPT"),
    ],
)
def test_attention_uses_small_deterministic_priority_table(
    signals: AttentionSignals,
    destination: str,
) -> None:
    assert decide_attention(signals).destination == destination


def test_higher_priority_signal_wins_over_noise() -> None:
    decision = decide_attention(
        AttentionSignals(urgent=True, goal_relevant=True, world_change=True, known_noise=True)
    )

    assert decision.destination == "INTERRUPT"
    assert decision.reasons == ("urgent",)


def test_attention_assessment_is_auditable_and_does_not_apply_effect(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="arquivo do Goal mudou",
        trace_id="trace_perception",
    )
    before_revision = get_world_revision(database_path)

    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(world_change=True),
    )

    restored = get_event(database_path, assessment.event.id)
    assert restored == assessment.event
    assert assessment.decision.destination == "UPDATE_WORLD"
    assert assessment.event.payload["observation_event_id"] == observation.event.id
    assert assessment.event.payload["effect_applied"] is False
    assert assessment.event.trace_id == "trace_perception"
    assert get_world_revision(database_path) == before_revision


def test_attention_rejects_non_observation_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    event = Event.create(kind="system.test", source="system")
    append_event(database_path, event)

    with pytest.raises(ValueError, match="não é uma observation"):
        assess_observation_attention(
            database_path,
            observation_event_id=event.id,
            signals=AttentionSignals(),
        )


def test_attend_can_be_materialized_as_persistent_pending_item(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="arquivo relevante mudou",
        trace_id="trace_attend",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(goal_relevant=True),
    )
    before_revision = get_world_revision(database_path)

    opening = open_attention_item(
        database_path,
        attention_event_id=assessment.event.id,
    )

    assert opening.created is True
    assert opening.item.assessment_event_id == assessment.event.id
    assert opening.item.observation_event_id == observation.event.id
    assert opening.item.summary == "arquivo relevante mudou"
    assert opening.item.reasons == ("goal_relevant",)
    assert opening.item.event.kind == "attention.item.opened"
    assert opening.item.event.source == "attention"
    assert opening.item.event.payload["status"] == "PENDING"
    assert opening.item.event.payload["focus_changed"] is False
    assert opening.item.event.payload["goal_created"] is False
    assert opening.item.event.payload["effect_applied"] is True
    assert get_world_revision(database_path) == before_revision
    assert get_attention_item(database_path, opening.item.event.id) == opening.item
    assert list_pending_attention_items(database_path) == (opening.item,)


def test_attention_item_opening_is_idempotent_per_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="calendar",
        signal_kind="deadline.changed",
        summary="prazo relevante mudou",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )

    first = open_attention_item(database_path, attention_event_id=assessment.event.id)
    second = open_attention_item(database_path, attention_event_id=assessment.event.id)

    assert first.created is True
    assert second.created is False
    assert second.item == first.item
    assert list_pending_attention_items(database_path) == (first.item,)


def test_attention_item_rejects_non_attend_destination(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="mudança candidata ao World",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(world_change=True),
    )

    with pytest.raises(ValueError, match="destino ATTEND"):
        open_attention_item(database_path, attention_event_id=assessment.event.id)
