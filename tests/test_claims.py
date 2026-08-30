from pathlib import Path

import pytest

from simon.attention import AttentionSignals, assess_observation_attention
from simon.claims import (
    Claim,
    ClaimConflictResolutionApplication,
    ClaimConflictResolutionProposal,
    ClaimEvidenceBinding,
    ProposedClaim,
    accept_ready_proposed_claim,
    apply_claim_conflict_resolution,
    bind_duplicate_claim_evidence,
    get_claim,
    get_claim_conflict_resolution_proposal,
    get_claim_validation,
    get_proposed_claim,
    insert_claim,
    list_active_claims,
    propose_claim_conflict_resolution,
    propose_claim_from_attention,
    set_current_claim,
    transition_claim,
    validate_proposed_claim,
)
from simon.entities import Entity, insert_entity
from simon.events import Event, append_event, get_event
from simon.perception import record_observation
from simon.storage import initialize_storage
from simon.world import get_world_revision


def _create_subject_and_evidence(tmp_path: Path) -> tuple[Path, Entity, Event]:
    database_path, _ = initialize_storage(tmp_path)
    subject = Entity.create(kind="project", name="Unlimited OCR")
    evidence = Event.create(kind="test.completed", source="test")
    insert_entity(database_path, subject)
    append_event(database_path, evidence)
    return database_path, subject, evidence


def test_claim_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, subject, evidence = _create_subject_and_evidence(tmp_path)
    claim = Claim.create(
        subject_id=subject.id,
        predicate="current_issue",
        value="generation_loop",
        epistemic_status="DIRECT_OBSERVATION",
        evidence_event_ids=(evidence.id,),
    )

    insert_claim(database_path, claim)
    restored = get_claim(database_path, claim.id)

    assert restored == claim


def test_contradictory_active_claims_are_not_silently_overwritten(tmp_path: Path) -> None:
    database_path, subject, evidence = _create_subject_and_evidence(tmp_path)
    first = Claim.create(
        subject_id=subject.id,
        predicate="status",
        value="working",
        epistemic_status="USER_REPORT",
        evidence_event_ids=(evidence.id,),
    )
    second = Claim.create(
        subject_id=subject.id,
        predicate="status",
        value="failing",
        epistemic_status="INFERRED",
        evidence_event_ids=(evidence.id,),
    )

    insert_claim(database_path, first)
    insert_claim(database_path, second)

    active = list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate="status",
    )

    assert active == (first, second)


def test_current_claim_supersedes_previous_value_but_not_same_value(tmp_path: Path) -> None:
    database_path, subject, evidence = _create_subject_and_evidence(tmp_path)

    first = set_current_claim(
        database_path,
        subject_id=subject.id,
        predicate="storage.schema_version",
        value=2,
        epistemic_status="DIRECT_OBSERVATION",
        evidence_event_ids=(evidence.id,),
    )
    repeated = set_current_claim(
        database_path,
        subject_id=subject.id,
        predicate="storage.schema_version",
        value=2,
        epistemic_status="DIRECT_OBSERVATION",
        evidence_event_ids=(evidence.id,),
    )
    replacement = set_current_claim(
        database_path,
        subject_id=subject.id,
        predicate="storage.schema_version",
        value=3,
        epistemic_status="DIRECT_OBSERVATION",
        evidence_event_ids=(evidence.id,),
    )

    assert repeated == first
    superseded = get_claim(database_path, first.id)
    assert superseded is not None
    assert superseded.status == "SUPERSEDED"
    assert replacement.status == "ACTIVE"
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate="storage.schema_version",
    ) == (replacement,)


def test_active_claim_can_be_retracted(tmp_path: Path) -> None:
    database_path, subject, evidence = _create_subject_and_evidence(tmp_path)
    claim = Claim.create(
        subject_id=subject.id,
        predicate="current_issue",
        value="generation_loop",
        epistemic_status="HYPOTHESIS",
        evidence_event_ids=(evidence.id,),
    )
    insert_claim(database_path, claim)

    retracted = transition_claim(database_path, claim.id, "RETRACTED")

    assert retracted.status == "RETRACTED"


def _create_update_world_assessment(
    tmp_path: Path,
    *,
    include_subject: bool = True,
) -> tuple[Path, Entity, str]:
    database_path, _ = initialize_storage(tmp_path)
    subject = Entity.create(kind="file", name="target.txt")
    insert_entity(database_path, subject)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="target.txt mudou",
        trace_id="trace_claim_proposal",
        related_entity_ids=(subject.id,) if include_subject else (),
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(world_change=True),
    )
    return database_path, subject, assessment.event.id


def test_update_world_attention_can_propose_claim_without_mutating_world(
    tmp_path: Path,
) -> None:
    database_path, subject, attention_event_id = _create_update_world_assessment(tmp_path)
    before_revision = get_world_revision(database_path)

    proposal = propose_claim_from_attention(
        database_path,
        attention_event_id=attention_event_id,
        subject_id=subject.id,
        predicate="content_state",
        value={"state": "changed"},
    )

    assert get_proposed_claim(database_path, proposal.event.id) == proposal
    assert proposal.event.kind == "world.claim.proposed"
    assert proposal.event.source == "perception"
    assert proposal.event.trace_id == "trace_claim_proposal"
    assert proposal.event.related_entity_ids == (subject.id,)
    assert proposal.subject_id == subject.id
    assert proposal.predicate == "content_state"
    assert proposal.value == {"state": "changed"}
    assert proposal.epistemic_status == "DIRECT_OBSERVATION"
    assert proposal.evidence_event_ids[1] == attention_event_id
    assert proposal.event.payload["effect_applied"] is False
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate="content_state",
    ) == ()
    assert get_world_revision(database_path) == before_revision


def test_proposed_claim_requires_update_world_attention(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    subject = Entity.create(kind="file", name="target.txt")
    insert_entity(database_path, subject)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="target.txt mudou",
        related_entity_ids=(subject.id,),
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(goal_relevant=True),
    )

    with pytest.raises(ValueError, match="destino UPDATE_WORLD"):
        propose_claim_from_attention(
            database_path,
            attention_event_id=assessment.event.id,
            subject_id=subject.id,
            predicate="content_state",
            value="changed",
        )


def test_proposed_claim_requires_subject_bound_to_observation(tmp_path: Path) -> None:
    database_path, subject, attention_event_id = _create_update_world_assessment(
        tmp_path,
        include_subject=False,
    )

    with pytest.raises(ValueError, match="relacionado à observation"):
        propose_claim_from_attention(
            database_path,
            attention_event_id=attention_event_id,
            subject_id=subject.id,
            predicate="content_state",
            value="changed",
        )


def test_proposed_claim_rejects_value_outside_json_contract(tmp_path: Path) -> None:
    database_path, subject, attention_event_id = _create_update_world_assessment(tmp_path)

    with pytest.raises(TypeError):
        propose_claim_from_attention(
            database_path,
            attention_event_id=attention_event_id,
            subject_id=subject.id,
            predicate="content_state",
            value={"unsupported": object()},
        )


def _create_proposed_claim(tmp_path: Path) -> tuple[Path, Entity, ProposedClaim]:
    database_path, subject, attention_event_id = _create_update_world_assessment(tmp_path)
    proposal = propose_claim_from_attention(
        database_path,
        attention_event_id=attention_event_id,
        subject_id=subject.id,
        predicate="content_state",
        value={"state": "changed"},
    )
    return database_path, subject, proposal


def test_proposed_claim_validation_is_ready_without_active_claim(tmp_path: Path) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    before_revision = get_world_revision(database_path)

    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )

    assert validation.outcome == "READY"
    assert validation.active_claim_ids == ()
    assert validation.matching_claim_ids == ()
    assert validation.conflicting_claim_ids == ()
    assert validation.reasons == ("no_active_claim",)
    assert validation.event.kind == "world.claim.validation.completed"
    assert validation.event.source == "world"
    assert validation.event.trace_id == proposal.event.trace_id
    assert validation.event.related_entity_ids == (subject.id,)
    assert validation.event.payload["effect_applied"] is False
    assert get_claim_validation(database_path, validation.event.id) == validation
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate="content_state",
    ) == ()
    assert get_world_revision(database_path) == before_revision


def test_proposed_claim_validation_detects_equivalent_active_claim(tmp_path: Path) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    active = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=proposal.value,
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, active)
    before_revision = get_world_revision(database_path)

    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )

    assert validation.outcome == "DUPLICATE"
    assert validation.active_claim_ids == (active.id,)
    assert validation.matching_claim_ids == (active.id,)
    assert validation.conflicting_claim_ids == ()
    assert validation.reasons == ("equivalent_active_claim",)
    assert get_world_revision(database_path) == before_revision


def test_proposed_claim_validation_detects_conflicting_active_claim(tmp_path: Path) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    active = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "stable"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, active)
    before_revision = get_world_revision(database_path)

    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )

    assert validation.outcome == "CONFLICT"
    assert validation.active_claim_ids == (active.id,)
    assert validation.matching_claim_ids == ()
    assert validation.conflicting_claim_ids == (active.id,)
    assert validation.reasons == ("active_claim_conflict",)
    assert get_world_revision(database_path) == before_revision


def test_conflict_takes_precedence_when_equivalent_and_conflicting_claims_coexist(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    matching = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=proposal.value,
        epistemic_status=proposal.epistemic_status,
    )
    conflicting = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "stable"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, matching)
    insert_claim(database_path, conflicting)

    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )

    assert validation.outcome == "CONFLICT"
    assert validation.matching_claim_ids == (matching.id,)
    assert validation.conflicting_claim_ids == (conflicting.id,)


def test_claim_validation_requires_proposed_claim_event(tmp_path: Path) -> None:
    database_path, _, attention_event_id = _create_update_world_assessment(tmp_path)

    with pytest.raises(ValueError, match="não é uma proposed claim"):
        validate_proposed_claim(
            database_path,
            proposed_claim_event_id=attention_event_id,
        )



def _create_duplicate_validation(
    tmp_path: Path,
) -> tuple[Path, Entity, ProposedClaim, Claim, object]:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    original_evidence = Event.create(kind="file.snapshot.recorded", source="test")
    append_event(database_path, original_evidence)
    active = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=proposal.value,
        epistemic_status=proposal.epistemic_status,
        evidence_event_ids=(original_evidence.id,),
    )
    insert_claim(database_path, active)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    assert validation.outcome == "DUPLICATE"
    return database_path, subject, proposal, active, validation


def test_duplicate_evidence_binding_appends_evidence_without_creating_claim_or_world_revision(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_duplicate_validation(
        tmp_path
    )
    before_revision = get_world_revision(database_path)

    binding = bind_duplicate_claim_evidence(
        database_path,
        validation_event_id=validation.event.id,
    )

    assert isinstance(binding, ClaimEvidenceBinding)
    assert binding.created is True
    assert binding.event.kind == "world.claim.evidence.bound"
    assert binding.event.source == "world"
    assert binding.validation_event_id == validation.event.id
    assert binding.proposed_claim_event_id == proposal.event.id
    assert tuple(claim.id for claim in binding.bound_claims) == (active.id,)
    assert binding.event.payload["basis"] == "DETERMINISTIC_EQUIVALENCE"
    assert binding.event.payload["claim_evidence_updated"] is True
    assert binding.event.payload["current_world_view_changed"] is False
    assert binding.event.payload["effect_applied"] is True
    assert proposal.evidence_event_ids[0] in binding.evidence_event_ids_added
    assert proposal.attention_event_id in binding.evidence_event_ids_added
    assert validation.event.id in binding.evidence_event_ids_added
    assert binding.event.id in binding.evidence_event_ids_added

    stored = get_claim(database_path, active.id)
    assert stored is not None
    assert stored.status == "ACTIVE"
    assert active.evidence_event_ids[0] in stored.evidence_event_ids
    assert all(
        event_id in stored.evidence_event_ids
        for event_id in binding.evidence_event_ids_added
    )
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate=proposal.predicate,
    ) == (stored,)
    assert get_event(database_path, binding.event.id) == binding.event
    assert get_world_revision(database_path) == before_revision


def test_duplicate_evidence_binding_is_idempotent_per_validation(tmp_path: Path) -> None:
    database_path, _, _, active, validation = _create_duplicate_validation(tmp_path)

    first = bind_duplicate_claim_evidence(
        database_path,
        validation_event_id=validation.event.id,
    )
    after_first = get_claim(database_path, active.id)
    after_first_revision = get_world_revision(database_path)
    repeated = bind_duplicate_claim_evidence(
        database_path,
        validation_event_id=validation.event.id,
    )

    assert repeated.created is False
    assert repeated.event == first.event
    assert repeated.bound_claims == first.bound_claims
    assert repeated.evidence_event_ids_added == first.evidence_event_ids_added
    assert get_claim(database_path, active.id) == after_first
    assert get_world_revision(database_path) == after_first_revision


def test_duplicate_evidence_binding_rechecks_belief_store_snapshot(tmp_path: Path) -> None:
    database_path, subject, proposal, active, validation = _create_duplicate_validation(
        tmp_path
    )
    late = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "late"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, late)
    before_binding = get_claim(database_path, active.id)
    before_revision = get_world_revision(database_path)

    with pytest.raises(ValueError, match="Belief Store mudou"):
        bind_duplicate_claim_evidence(
            database_path,
            validation_event_id=validation.event.id,
        )

    assert get_claim(database_path, active.id) == before_binding
    assert get_world_revision(database_path) == before_revision


@pytest.mark.parametrize("outcome_kind", ["READY", "CONFLICT"])
def test_duplicate_evidence_binding_rejects_non_duplicate_validation(
    tmp_path: Path,
    outcome_kind: str,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    if outcome_kind == "CONFLICT":
        insert_claim(
            database_path,
            Claim.create(
                subject_id=subject.id,
                predicate=proposal.predicate,
                value={"state": "other"},
                epistemic_status=proposal.epistemic_status,
            ),
        )
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    assert validation.outcome == outcome_kind

    with pytest.raises(ValueError, match="validation DUPLICATE"):
        bind_duplicate_claim_evidence(
            database_path,
            validation_event_id=validation.event.id,
        )


def test_duplicate_evidence_binding_updates_all_equivalent_active_claims(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    first = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=proposal.value,
        epistemic_status=proposal.epistemic_status,
    )
    second = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=proposal.value,
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, first)
    insert_claim(database_path, second)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    assert validation.outcome == "DUPLICATE"
    before_revision = get_world_revision(database_path)

    binding = bind_duplicate_claim_evidence(
        database_path,
        validation_event_id=validation.event.id,
    )

    assert tuple(claim.id for claim in binding.bound_claims) == (
        first.id,
        second.id,
    )
    for claim_id in (first.id, second.id):
        stored = get_claim(database_path, claim_id)
        assert stored is not None
        assert all(
            event_id in stored.evidence_event_ids
            for event_id in binding.evidence_event_ids_added
        )
    assert get_world_revision(database_path) == before_revision


def test_ready_proposed_claim_can_be_accepted_only_by_explicit_user_authority(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    before_revision = get_world_revision(database_path)

    receipt = accept_ready_proposed_claim(
        database_path,
        validation_event_id=validation.event.id,
    )

    assert receipt.created is True
    assert receipt.claim.status == "ACTIVE"
    assert receipt.claim.subject_id == subject.id
    assert receipt.claim.predicate == proposal.predicate
    assert receipt.claim.value == proposal.value
    assert receipt.claim.epistemic_status == "DIRECT_OBSERVATION"
    assert receipt.event.kind == "world.claim.accepted"
    assert receipt.event.source == "user"
    assert receipt.event.payload["authority"] == "USER_CONFIRMATION"
    assert receipt.event.payload["claim_id"] == receipt.claim.id
    assert validation.event.id in receipt.claim.evidence_event_ids
    assert receipt.event.id in receipt.claim.evidence_event_ids
    assert get_claim(database_path, receipt.claim.id) == receipt.claim
    assert get_event(database_path, receipt.event.id) == receipt.event
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate=proposal.predicate,
    ) == (receipt.claim,)
    assert get_world_revision(database_path) == before_revision + 1


def test_ready_claim_acceptance_is_idempotent_for_same_proposal(tmp_path: Path) -> None:
    database_path, _, proposal = _create_proposed_claim(tmp_path)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )

    first = accept_ready_proposed_claim(
        database_path,
        validation_event_id=validation.event.id,
    )
    after_first_revision = get_world_revision(database_path)
    repeated = accept_ready_proposed_claim(
        database_path,
        validation_event_id=validation.event.id,
    )

    assert first.created is True
    assert repeated.created is False
    assert repeated.claim == first.claim
    assert repeated.event == first.event
    assert get_world_revision(database_path) == after_first_revision


@pytest.mark.parametrize("active_value", [{"state": "changed"}, {"state": "stable"}])
def test_claim_acceptance_rejects_non_ready_validation(
    tmp_path: Path,
    active_value: object,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    active = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value=active_value,
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, active)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    before_revision = get_world_revision(database_path)

    with pytest.raises(ValueError, match="validation READY"):
        accept_ready_proposed_claim(
            database_path,
            validation_event_id=validation.event.id,
        )

    assert get_world_revision(database_path) == before_revision
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate=proposal.predicate,
    ) == (active,)


def test_ready_claim_acceptance_rechecks_belief_store_atomically(tmp_path: Path) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    late_claim = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "late"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, late_claim)
    before_revision = get_world_revision(database_path)

    with pytest.raises(ValueError, match="Belief Store mudou"):
        accept_ready_proposed_claim(
            database_path,
            validation_event_id=validation.event.id,
        )

    assert get_world_revision(database_path) == before_revision
    assert list_active_claims(
        database_path,
        subject_id=subject.id,
        predicate=proposal.predicate,
    ) == (late_claim,)


def test_claim_acceptance_does_not_generalize_beyond_direct_observation(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    forged = Event.create(
        kind="world.claim.proposed",
        source="perception",
        payload={
            **proposal.event.payload,
            "epistemic_status": "INFERRED",
        },
        trace_id=proposal.event.trace_id,
        related_entity_ids=(subject.id,),
    )
    append_event(database_path, forged)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=forged.id,
    )
    assert validation.outcome == "READY"

    with pytest.raises(ValueError, match="DIRECT_OBSERVATION"):
        accept_ready_proposed_claim(
            database_path,
            validation_event_id=validation.event.id,
        )


def _create_conflicting_validation(
    tmp_path: Path,
) -> tuple[Path, Entity, ProposedClaim, Claim, object]:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    active = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "stable"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, active)
    validation = validate_proposed_claim(
        database_path,
        proposed_claim_event_id=proposal.event.id,
    )
    assert validation.outcome == "CONFLICT"
    return database_path, subject, proposal, active, validation


def test_conflict_resolution_can_propose_proposed_claim_as_winner_without_effect(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    before_revision = get_world_revision(database_path)

    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=proposal.event.id,
    )

    assert isinstance(resolution, ClaimConflictResolutionProposal)
    assert resolution.event.kind == "world.claim.conflict.resolution.proposed"
    assert resolution.event.source == "user"
    assert resolution.validation_event_id == validation.event.id
    assert resolution.proposed_claim_event_id == proposal.event.id
    assert resolution.winner_kind == "PROPOSED_CLAIM"
    assert resolution.winner_id == proposal.event.id
    assert resolution.expected_active_claim_ids == (active.id,)
    assert resolution.conflicting_claim_ids == (active.id,)
    assert resolution.event.payload["authority"] == "USER_DECISION"
    assert resolution.event.payload["effect_applied"] is False
    assert get_claim_conflict_resolution_proposal(
        database_path, resolution.event.id
    ) == resolution
    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (active,)
    assert get_world_revision(database_path) == before_revision


def test_conflict_resolution_can_select_active_claim_as_winner(tmp_path: Path) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    before_revision = get_world_revision(database_path)

    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=active.id,
    )

    assert resolution.winner_kind == "ACTIVE_CLAIM"
    assert resolution.winner_id == active.id
    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (active,)
    assert get_world_revision(database_path) == before_revision


def test_conflict_resolution_requires_conflict_validation(tmp_path: Path) -> None:
    database_path, _, proposal = _create_proposed_claim(tmp_path)
    validation = validate_proposed_claim(
        database_path, proposed_claim_event_id=proposal.event.id
    )
    assert validation.outcome == "READY"

    with pytest.raises(ValueError, match="validation CONFLICT"):
        propose_claim_conflict_resolution(
            database_path,
            validation_event_id=validation.event.id,
            winner_id=proposal.event.id,
        )


def test_conflict_resolution_rejects_winner_outside_validated_candidates(
    tmp_path: Path,
) -> None:
    database_path, subject, _proposal, _, validation = _create_conflicting_validation(
        tmp_path
    )
    outsider = Claim.create(
        subject_id=subject.id,
        predicate="other_predicate",
        value="outside",
        epistemic_status="DIRECT_OBSERVATION",
    )
    insert_claim(database_path, outsider)

    with pytest.raises(ValueError, match="winner_id"):
        propose_claim_conflict_resolution(
            database_path,
            validation_event_id=validation.event.id,
            winner_id=outsider.id,
        )


def test_conflict_resolution_rechecks_validation_snapshot_before_proposing(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    late = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "later"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, late)
    before_revision = get_world_revision(database_path)

    with pytest.raises(ValueError, match="Belief Store mudou"):
        propose_claim_conflict_resolution(
            database_path,
            validation_event_id=validation.event.id,
            winner_id=active.id,
        )

    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (active, late)
    assert get_world_revision(database_path) == before_revision


def test_conflict_resolution_is_idempotent_and_immutable_per_validation(
    tmp_path: Path,
) -> None:
    database_path, _, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )

    first = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=active.id,
    )
    repeated = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=active.id,
    )

    assert repeated == first

    with pytest.raises(ValueError, match="proposta de resolução diferente"):
        propose_claim_conflict_resolution(
            database_path,
            validation_event_id=validation.event.id,
            winner_id=proposal.event.id,
        )

def test_conflict_resolution_application_materializes_proposed_winner_atomically(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=proposal.event.id,
    )
    before_revision = get_world_revision(database_path)

    application = apply_claim_conflict_resolution(
        database_path,
        resolution_event_id=resolution.event.id,
    )

    assert isinstance(application, ClaimConflictResolutionApplication)
    assert application.event.kind == "world.claim.conflict.resolution.applied"
    assert application.event.source == "world"
    assert application.resolution_event_id == resolution.event.id
    assert application.validation_event_id == validation.event.id
    assert application.proposed_claim_event_id == proposal.event.id
    assert application.winner_kind == "PROPOSED_CLAIM"
    assert application.winner_claim_created is True
    assert application.belief_store_changed is True
    assert application.created is True
    assert application.superseded_claim_ids == (active.id,)
    assert application.event.payload["authority"] == "USER_DECISION"
    assert application.event.payload["authority_event_id"] == resolution.event.id
    assert application.event.payload["effect_applied"] is True
    assert application.winner_claim.value == proposal.value
    assert application.winner_claim.epistemic_status == proposal.epistemic_status
    assert validation.event.id in application.winner_claim.evidence_event_ids
    assert resolution.event.id in application.winner_claim.evidence_event_ids
    assert application.event.id in application.winner_claim.evidence_event_ids
    stored_active = get_claim(database_path, active.id)
    assert stored_active is not None
    assert stored_active.status == "SUPERSEDED"
    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (application.winner_claim,)
    assert get_world_revision(database_path) == before_revision + 1


def test_conflict_resolution_application_can_keep_single_active_winner_without_world_change(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=active.id,
    )
    before_revision = get_world_revision(database_path)

    application = apply_claim_conflict_resolution(
        database_path,
        resolution_event_id=resolution.event.id,
    )

    assert application.winner_kind == "ACTIVE_CLAIM"
    assert application.winner_claim == active
    assert application.winner_claim_created is False
    assert application.superseded_claim_ids == ()
    assert application.belief_store_changed is False
    assert application.created is True
    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (active,)
    assert get_world_revision(database_path) == before_revision


def test_conflict_resolution_application_supersedes_other_active_claims_only(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal = _create_proposed_claim(tmp_path)
    winner = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "stable"},
        epistemic_status=proposal.epistemic_status,
    )
    loser = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "legacy"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, winner)
    insert_claim(database_path, loser)
    validation = validate_proposed_claim(
        database_path, proposed_claim_event_id=proposal.event.id
    )
    assert validation.outcome == "CONFLICT"
    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=winner.id,
    )
    before_revision = get_world_revision(database_path)

    application = apply_claim_conflict_resolution(
        database_path, resolution_event_id=resolution.event.id
    )

    assert application.winner_claim == winner
    assert application.superseded_claim_ids == (loser.id,)
    assert application.winner_claim_created is False
    assert application.belief_store_changed is True
    stored_winner = get_claim(database_path, winner.id)
    stored_loser = get_claim(database_path, loser.id)
    assert stored_winner is not None
    assert stored_loser is not None
    assert stored_winner.status == "ACTIVE"
    assert stored_loser.status == "SUPERSEDED"
    assert list_active_claims(
        database_path, subject_id=subject.id, predicate=proposal.predicate
    ) == (winner,)
    assert get_world_revision(database_path) == before_revision + 1


def test_conflict_resolution_application_rechecks_resolution_snapshot(
    tmp_path: Path,
) -> None:
    database_path, subject, proposal, active, validation = _create_conflicting_validation(
        tmp_path
    )
    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=proposal.event.id,
    )
    late = Claim.create(
        subject_id=subject.id,
        predicate=proposal.predicate,
        value={"state": "late"},
        epistemic_status=proposal.epistemic_status,
    )
    insert_claim(database_path, late)
    before_revision = get_world_revision(database_path)

    with pytest.raises(ValueError, match="Belief Store mudou"):
        apply_claim_conflict_resolution(
            database_path, resolution_event_id=resolution.event.id
        )

    stored_active = get_claim(database_path, active.id)
    stored_late = get_claim(database_path, late.id)
    assert stored_active is not None
    assert stored_late is not None
    assert stored_active.status == "ACTIVE"
    assert stored_late.status == "ACTIVE"
    assert get_world_revision(database_path) == before_revision


def test_conflict_resolution_application_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path, _, proposal, _, validation = _create_conflicting_validation(tmp_path)
    resolution = propose_claim_conflict_resolution(
        database_path,
        validation_event_id=validation.event.id,
        winner_id=proposal.event.id,
    )

    first = apply_claim_conflict_resolution(
        database_path, resolution_event_id=resolution.event.id
    )
    after_first_revision = get_world_revision(database_path)
    repeated = apply_claim_conflict_resolution(
        database_path, resolution_event_id=resolution.event.id
    )

    assert repeated.created is False
    assert repeated.event == first.event
    assert repeated.winner_claim == first.winner_claim
    assert repeated.superseded_claim_ids == first.superseded_claim_ids
    assert repeated.belief_store_changed is True
    assert get_world_revision(database_path) == after_first_revision


def test_conflict_resolution_application_requires_resolution_event(tmp_path: Path) -> None:
    database_path, _, _, _, validation = _create_conflicting_validation(tmp_path)

    with pytest.raises(ValueError, match="resolution.proposed existente"):
        apply_claim_conflict_resolution(
            database_path, resolution_event_id=validation.event.id
        )

