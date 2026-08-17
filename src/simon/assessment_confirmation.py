from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from simon.events import Event
from simon.verification import (
    VerificationResult,
    create_verification_result_in_connection,
    get_verification_result,
    get_verification_result_in_connection,
    list_verification_results,
    list_verification_results_in_connection,
)

CONFIRMATION_STRENGTH = 3


@dataclass(frozen=True, slots=True)
class AssessmentConfirmationSpec:
    action_kind: str
    confirmation_type: str


@dataclass(frozen=True, slots=True)
class AssessmentConfirmationReceipt:
    assessment: VerificationResult
    verification: VerificationResult
    confirmation_event_id: str
    created: bool


_CONFIRMABLE_ASSESSMENTS = {
    "user.ask.semantic": AssessmentConfirmationSpec(
        action_kind="user.ask",
        confirmation_type="user.ask.assessment_confirmation",
    ),
    "cognition.analyze.semantic": AssessmentConfirmationSpec(
        action_kind="cognition.analyze",
        confirmation_type="cognition.analyze.assessment_confirmation",
    ),
}


def confirm_action_assessment(
    database_path: Path,
    *,
    assessment_verification_id: str,
    trace_id: str | None = None,
) -> AssessmentConfirmationReceipt:
    """Promove um assessment SATISFIED autorizado pelo usuário para VERIFIED."""
    assessment = get_verification_result(database_path, assessment_verification_id)
    if assessment is None:
        raise ValueError(f"Verification de assessment não encontrada: {assessment_verification_id}")
    spec = _confirmation_spec(assessment)
    _validate_confirmable_assessment(assessment)

    existing = _find_existing_confirmation(
        database_path,
        assessment=assessment,
        spec=spec,
    )
    if existing is not None:
        return existing

    confirmation_trace_id = trace_id or f"trc_{uuid4().hex}"
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = get_verification_result_in_connection(connection, assessment.id)
        if current is None:
            raise ValueError(f"Verification de assessment não encontrada: {assessment.id}")
        current_spec = _confirmation_spec(current)
        _validate_confirmable_assessment(current)

        existing = _find_existing_confirmation_in_connection(
            connection,
            assessment=current,
            spec=current_spec,
        )
        if existing is not None:
            return existing

        action_row = connection.execute(
            "SELECT goal_id, plan_id, step_id, status, kind FROM actions WHERE id = ?",
            (current.subject_id,),
        ).fetchone()
        if action_row is None:
            raise ValueError(f"action não encontrada: {current.subject_id}")
        if str(action_row[3]) != "COMPLETED" or str(action_row[4]) != current_spec.action_kind:
            raise ValueError(
                "confirmação exige action "
                f"{current_spec.action_kind} COMPLETED"
            )

        latest_attempt = connection.execute(
            """
            SELECT id
            FROM actions
            WHERE plan_id = ? AND step_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (str(action_row[1]), str(action_row[2])),
        ).fetchone()
        if latest_attempt is None or str(latest_attempt[0]) != current.subject_id:
            raise ValueError("confirmação exige a tentativa mais recente do step")

        assessment_type = _assessment_type(current)
        event = Event.create(
            kind="verification.assessment.confirmed",
            source="user",
            payload={
                "assessment_verification_id": current.id,
                "action_id": current.subject_id,
                "assessment_type": assessment_type,
                "assessment_verdict": "SATISFIED",
            },
            trace_id=confirmation_trace_id,
            goal_id=str(action_row[0]),
        )
        _insert_event(connection, event)

        evidence_event_ids = tuple(dict.fromkeys((*current.evidence_event_ids, event.id)))
        verification = create_verification_result_in_connection(
            connection,
            subject_type="ACTION",
            subject_id=current.subject_id,
            criteria=current.criteria,
            status="VERIFIED",
            evidence_event_ids=evidence_event_ids,
            observed={
                "verification_type": current_spec.confirmation_type,
                "confirmed_assessment_id": current.id,
                "assessment_type": assessment_type,
                "assessment_verdict": "SATISFIED",
                "confirmation_event_id": event.id,
                "confirmed_by": "user",
            },
            strength=CONFIRMATION_STRENGTH,
        )

    return AssessmentConfirmationReceipt(
        assessment=current,
        verification=verification,
        confirmation_event_id=event.id,
        created=True,
    )


def _validate_confirmable_assessment(assessment: VerificationResult) -> None:
    if assessment.subject_type != "ACTION":
        raise ValueError("confirmação exige assessment de ACTION")
    if assessment.status != "ASSESSED":
        raise ValueError("confirmação exige VerificationResult ASSESSED")
    _confirmation_spec(assessment)
    if assessment.observed.get("verdict") != "SATISFIED":
        raise ValueError("somente assessment SATISFIED pode ser confirmado como VERIFIED")


def _assessment_type(assessment: VerificationResult) -> str:
    value = assessment.observed.get("assessment_type")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("VerificationResult não possui assessment_type confirmável")
    return value.strip()


def _confirmation_spec(assessment: VerificationResult) -> AssessmentConfirmationSpec:
    assessment_type = _assessment_type(assessment)
    spec = _CONFIRMABLE_ASSESSMENTS.get(assessment_type)
    if spec is None:
        raise ValueError(
            "VerificationResult não representa assessment confirmável: "
            f"{assessment_type}"
        )
    return spec


def _find_existing_confirmation(
    database_path: Path,
    *,
    assessment: VerificationResult,
    spec: AssessmentConfirmationSpec,
) -> AssessmentConfirmationReceipt | None:
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=assessment.subject_id,
    )
    return _confirmation_from_results(assessment, spec, results)


def _find_existing_confirmation_in_connection(
    connection: sqlite3.Connection,
    *,
    assessment: VerificationResult,
    spec: AssessmentConfirmationSpec,
) -> AssessmentConfirmationReceipt | None:
    results = list_verification_results_in_connection(
        connection,
        subject_type="ACTION",
        subject_id=assessment.subject_id,
    )
    return _confirmation_from_results(assessment, spec, results)


def _confirmation_from_results(
    assessment: VerificationResult,
    spec: AssessmentConfirmationSpec,
    results: tuple[VerificationResult, ...],
) -> AssessmentConfirmationReceipt | None:
    for result in reversed(results):
        if result.status != "VERIFIED":
            continue
        if result.observed.get("verification_type") != spec.confirmation_type:
            continue
        if result.observed.get("confirmed_assessment_id") != assessment.id:
            continue
        event_id = result.observed.get("confirmation_event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise TypeError("confirmation_event_id persistido possui tipo inválido")
        return AssessmentConfirmationReceipt(
            assessment=assessment,
            verification=result,
            confirmation_event_id=event_id,
            created=False,
        )
    return None


def _insert_event(connection: sqlite3.Connection, event: Event) -> None:
    connection.execute(
        """
        INSERT INTO events (
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.kind,
            event.occurred_at.isoformat(),
            event.source,
            json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
            event.trace_id,
            json.dumps(event.related_entity_ids, separators=(",", ":")),
            event.goal_id,
            event.experience_id,
        ),
    )
