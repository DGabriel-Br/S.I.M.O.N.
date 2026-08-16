from pathlib import Path

from simon.claims import (
    Claim,
    get_claim,
    insert_claim,
    list_active_claims,
    set_current_claim,
    transition_claim,
)
from simon.entities import Entity, insert_entity
from simon.events import Event, append_event
from simon.storage import initialize_storage


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
