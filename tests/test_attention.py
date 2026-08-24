from pathlib import Path

import pytest

from simon.attention import AttentionSignals, assess_observation_attention, decide_attention
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
