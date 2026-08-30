from pathlib import Path

import pytest

from simon.attention import (
    AttentionSignals,
    assess_observation_attention,
    decide_attention,
    get_attention_item,
    get_attention_item_review,
    list_pending_attention_items,
    open_attention_item,
    review_attention_item,
)
from simon.cognition import GoalProposal
from simon.events import Event, append_event, get_event
from simon.goal_intake import accept_goal_proposal
from simon.perception import record_observation
from simon.resume import reconstruct_resume_state
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

@pytest.mark.parametrize(
    ("decision", "status"),
    [
        ("DISMISS", "DISMISSED"),
        ("ACKNOWLEDGE", "ACKNOWLEDGED"),
    ],
)
def test_attention_item_can_be_closed_by_explicit_user_review(
    tmp_path: Path,
    decision: str,
    status: str,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="calendar",
        signal_kind="deadline.changed",
        summary="prazo acompanhado mudou",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)
    before_revision = get_world_revision(database_path)

    receipt = review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision=decision,
    )

    assert receipt.created is True
    assert receipt.review.event.kind == "attention.item.reviewed"
    assert receipt.review.event.source == "user"
    assert receipt.review.decision == decision
    assert receipt.review.status == status
    assert receipt.review.event.payload["authority"] == "USER_DECISION"
    assert receipt.review.event.payload["focus_changed"] is False
    assert receipt.review.event.payload["goal_created"] is False
    assert receipt.review.goal_proposal_event_id is None
    assert receipt.goal_proposal_event is None
    assert list_pending_attention_items(database_path) == ()
    assert get_attention_item_review(database_path, opening.item.event.id) == receipt.review
    assert get_world_revision(database_path) == before_revision


def test_attention_item_review_is_idempotent_and_decision_is_terminal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="arquivo relevante mudou",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(goal_relevant=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)

    first = review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision="ACKNOWLEDGE",
    )
    second = review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision="ACKNOWLEDGE",
    )

    assert first.created is True
    assert second.created is False
    assert second.review == first.review

    with pytest.raises(ValueError, match="decisão diferente"):
        review_attention_item(
            database_path,
            attention_item_event_id=opening.item.event.id,
            decision="DISMISS",
        )


def test_attention_item_can_materialize_goal_proposal_without_creating_goal(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="monitor",
        signal_kind="service.degraded",
        summary="serviço acompanhado degradou",
        trace_id="trace_attention_goal",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)
    proposal = GoalProposal(
        title="Restaurar serviço acompanhado",
        desired_state="O serviço acompanhado voltou ao estado operacional esperado.",
        success_criteria=["O serviço responde normalmente."],
    )

    receipt = review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision="PROPOSE_GOAL",
        goal_proposal=proposal,
    )

    assert receipt.review.status == "GOAL_PROPOSED"
    assert receipt.review.event.payload["goal_created"] is False
    assert receipt.goal_proposal_event is not None
    assert receipt.goal_proposal_event.kind == "attention.goal_proposal.completed"
    assert receipt.goal_proposal_event.source == "user"
    assert receipt.goal_proposal_event.payload["origin"] == "ATTENTION_REVIEW"
    assert receipt.goal_proposal_event.payload["authority"] == "USER_DECISION"
    assert receipt.goal_proposal_event.payload["materialized_by"] == "attention"
    assert receipt.goal_proposal_event.payload["proposal"] == proposal.model_dump(mode="json")
    assert list_pending_attention_items(database_path) == ()
    assert reconstruct_resume_state(database_path).open_goals == ()

    repeated = review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision="PROPOSE_GOAL",
        goal_proposal=proposal,
    )
    assert repeated.created is False
    assert repeated.review == receipt.review
    assert repeated.goal_proposal_event == receipt.goal_proposal_event

    acceptance = accept_goal_proposal(database_path, receipt.goal_proposal_event.id)

    assert acceptance.created is True
    assert acceptance.goal.title == proposal.title
    assert acceptance.goal.origin == "USER"
    assert acceptance.goal.status == "ACTIVE"


def test_attention_goal_proposal_requires_structured_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="monitor",
        signal_kind="service.degraded",
        summary="serviço acompanhado degradou",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)

    with pytest.raises(ValueError, match="proposta de Goal estruturada"):
        review_attention_item(
            database_path,
            attention_item_event_id=opening.item.event.id,
            decision="PROPOSE_GOAL",
        )

    assert list_pending_attention_items(database_path) == (opening.item,)


def test_attention_goal_proposal_review_rejects_different_payload_on_retry(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="monitor",
        signal_kind="service.degraded",
        summary="serviço acompanhado degradou",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)
    first = GoalProposal(
        title="Restaurar serviço",
        desired_state="O serviço voltou ao normal.",
        success_criteria=["O serviço responde normalmente."],
    )
    second = GoalProposal(
        title="Investigar serviço",
        desired_state="A causa da degradação está identificada.",
        success_criteria=["Existe evidência verificável da causa."],
    )
    review_attention_item(
        database_path,
        attention_item_event_id=opening.item.event.id,
        decision="PROPOSE_GOAL",
        goal_proposal=first,
    )

    with pytest.raises(ValueError, match="review é imutável"):
        review_attention_item(
            database_path,
            attention_item_event_id=opening.item.event.id,
            decision="PROPOSE_GOAL",
            goal_proposal=second,
        )
