from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from simon.events import Event
from simon.goals import Goal
from simon.verification import (
    VerificationResult,
    create_verification_result_in_connection,
    get_verification_result,
    get_verification_result_in_connection,
    list_verification_results_in_connection,
)

ASSESSMENT_TYPE = "goal.semantic"
CONFIRMATION_TYPE = "goal.assessment_confirmation"
CONFIRMATION_STRENGTH = 3


@dataclass(frozen=True, slots=True)
class GoalCompletionReceipt:
    assessment: VerificationResult
    verification: VerificationResult
    goal: Goal
    confirmation_event_id: str
    completion_event_id: str
    created: bool


def complete_goal_from_assessment(
    database_path: Path,
    *,
    assessment_verification_id: str,
    trace_id: str | None = None,
) -> GoalCompletionReceipt:
    assessment = get_verification_result(database_path, assessment_verification_id)
    if assessment is None:
        raise ValueError(f"Verification de assessment não encontrada: {assessment_verification_id}")
    _validate_goal_assessment(assessment)

    existing = _find_existing_completion(database_path, assessment=assessment)
    if existing is not None:
        return existing

    completion_trace_id = trace_id or f"trc_{uuid4().hex}"
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = get_verification_result_in_connection(connection, assessment.id)
        if current is None:
            raise ValueError(f"Verification de assessment não encontrada: {assessment.id}")
        _validate_goal_assessment(current)

        existing = _find_existing_completion_in_connection(connection, assessment=current)
        if existing is not None:
            return existing

        goal = _goal_in_connection(connection, current.subject_id)
        if goal.status != "ACTIVE":
            raise ValueError(f"conclusão de Goal exige goal ACTIVE: {goal.status}")
        if tuple(current.criteria) != goal.success_criteria:
            raise RuntimeError("critérios do Goal mudaram desde o assessment")

        _require_latest_goal_assessment(connection, current)
        plan_id, plan_revision, plan_completion_event_id = _assessment_plan(current)
        _validate_completed_plan(
            connection,
            goal_id=goal.id,
            plan_id=plan_id,
            plan_revision=plan_revision,
            completion_event_id=plan_completion_event_id,
        )

        confirmation_event = Event.create(
            kind="verification.goal_assessment.confirmed",
            source="user",
            payload={
                "assessment_verification_id": current.id,
                "goal_id": goal.id,
                "assessment_type": ASSESSMENT_TYPE,
                "assessment_verdict": "SATISFIED",
                "plan_id": plan_id,
                "plan_revision": plan_revision,
            },
            trace_id=completion_trace_id,
            goal_id=goal.id,
        )
        _insert_event(connection, confirmation_event)

        evidence_event_ids = tuple(
            dict.fromkeys((*current.evidence_event_ids, confirmation_event.id))
        )
        verification = create_verification_result_in_connection(
            connection,
            subject_type="GOAL",
            subject_id=goal.id,
            criteria=goal.success_criteria,
            status="VERIFIED",
            evidence_event_ids=evidence_event_ids,
            observed={
                "verification_type": CONFIRMATION_TYPE,
                "confirmed_assessment_id": current.id,
                "assessment_type": ASSESSMENT_TYPE,
                "assessment_verdict": "SATISFIED",
                "plan_id": plan_id,
                "plan_revision": plan_revision,
                "plan_completion_event_id": plan_completion_event_id,
                "confirmation_event_id": confirmation_event.id,
                "confirmed_by": "user",
            },
            strength=CONFIRMATION_STRENGTH,
        )

        completed_goal = _transition_goal_to_completed(connection, goal)
        completion_event = Event.create(
            kind="goal.completed",
            source="system",
            payload={
                "goal_id": completed_goal.id,
                "goal_verification_id": verification.id,
                "confirmed_assessment_id": current.id,
                "plan_id": plan_id,
                "plan_revision": plan_revision,
                "previous_status": "ACTIVE",
                "status": "COMPLETED",
            },
            trace_id=completion_trace_id,
            goal_id=completed_goal.id,
        )
        _insert_event(connection, completion_event)

    return GoalCompletionReceipt(
        assessment=current,
        verification=verification,
        goal=completed_goal,
        confirmation_event_id=confirmation_event.id,
        completion_event_id=completion_event.id,
        created=True,
    )


def _validate_goal_assessment(assessment: VerificationResult) -> None:
    if assessment.subject_type != "GOAL":
        raise ValueError("conclusão exige assessment de GOAL")
    if assessment.status != "ASSESSED":
        raise ValueError("conclusão exige VerificationResult ASSESSED")
    if assessment.observed.get("assessment_type") != ASSESSMENT_TYPE:
        raise ValueError("VerificationResult não representa assessment goal.semantic")
    if assessment.observed.get("verdict") != "SATISFIED":
        raise ValueError("somente assessment SATISFIED pode concluir o Goal")

    raw_criteria = assessment.observed.get("criterion_assessments")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ValueError("assessment de Goal não possui criterion_assessments válidos")
    for item in raw_criteria:
        if not isinstance(item, dict) or item.get("verdict") != "SATISFIED":
            raise ValueError("conclusão exige todos os critérios com verdict SATISFIED")

    missing_evidence = assessment.observed.get("missing_evidence")
    if not isinstance(missing_evidence, list):
        raise TypeError("assessment de Goal possui missing_evidence inválido")
    if missing_evidence:
        raise ValueError("assessment SATISFIED ainda declara evidência ausente")

    _assessment_plan(assessment)


def _assessment_plan(assessment: VerificationResult) -> tuple[str, int, str]:
    plan_id = assessment.observed.get("plan_id")
    plan_revision = assessment.observed.get("plan_revision")
    completion_event_id = assessment.observed.get("plan_completion_event_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError("assessment de Goal possui plan_id inválido")
    if isinstance(plan_revision, bool) or not isinstance(plan_revision, int):
        raise TypeError("assessment de Goal possui plan_revision inválida")
    if not isinstance(completion_event_id, str) or not completion_event_id.strip():
        raise ValueError("assessment de Goal possui plan_completion_event_id inválido")
    return plan_id.strip(), plan_revision, completion_event_id.strip()


def _require_latest_goal_assessment(
    connection: sqlite3.Connection,
    assessment: VerificationResult,
) -> None:
    results = list_verification_results_in_connection(
        connection,
        subject_type="GOAL",
        subject_id=assessment.subject_id,
    )
    latest: VerificationResult | None = None
    for result in results:
        if result.status != "ASSESSED":
            continue
        if result.observed.get("assessment_type") != ASSESSMENT_TYPE:
            continue
        latest = result
    if latest is None or latest.id != assessment.id:
        raise ValueError("conclusão exige o assessment goal.semantic mais recente")


def _validate_completed_plan(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    plan_id: str,
    plan_revision: int,
    completion_event_id: str,
) -> None:
    row = connection.execute(
        """
        SELECT id, revision, status
        FROM plans
        WHERE id = ? AND goal_id = ?
        """,
        (plan_id, goal_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"Plan do assessment não encontrado: {plan_id}")
    if int(row[1]) != plan_revision:
        raise RuntimeError("revisão do Plan diverge do assessment")
    if str(row[2]) != "COMPLETED":
        raise ValueError(f"Plan do assessment não está COMPLETED: {row[2]}")

    latest = connection.execute(
        """
        SELECT id, revision
        FROM plans
        WHERE goal_id = ? AND status = 'COMPLETED'
        ORDER BY revision DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (goal_id,),
    ).fetchone()
    if latest is None or str(latest[0]) != plan_id or int(latest[1]) != plan_revision:
        raise ValueError("assessment não corresponde ao Plan COMPLETED mais recente")

    event_row = connection.execute(
        """
        SELECT kind, source, payload_json, goal_id
        FROM events
        WHERE id = ?
        """,
        (completion_event_id,),
    ).fetchone()
    if event_row is None:
        raise ValueError(f"Event plan.completed não encontrado: {completion_event_id}")
    if str(event_row[0]) != "plan.completed" or str(event_row[1]) != "system":
        raise ValueError("assessment referencia Event que não é plan.completed do system")
    if str(event_row[3]) != goal_id:
        raise ValueError("plan.completed pertence a outro Goal")
    payload = json.loads(str(event_row[2]))
    if not isinstance(payload, dict):
        raise TypeError("payload de plan.completed inválido")
    if payload.get("plan_id") != plan_id or payload.get("plan_revision") != plan_revision:
        raise ValueError("plan.completed diverge do Plan avaliado")


def _goal_in_connection(connection: sqlite3.Connection, goal_id: str) -> Goal:
    row = connection.execute(
        """
        SELECT
            id,
            title,
            origin,
            parent_goal_id,
            desired_state_json,
            success_criteria_json,
            status,
            created_at,
            updated_at
        FROM goals
        WHERE id = ?
        """,
        (goal_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    return _goal_from_row(row)


def _transition_goal_to_completed(
    connection: sqlite3.Connection,
    goal: Goal,
) -> Goal:
    updated_at = datetime.now(UTC)
    cursor = connection.execute(
        """
        UPDATE goals
        SET status = 'COMPLETED', updated_at = ?
        WHERE id = ? AND status = 'ACTIVE'
        """,
        (updated_at.isoformat(), goal.id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"Goal mudou durante conclusão: {goal.id}")
    completed = _goal_in_connection(connection, goal.id)
    if completed.status != "COMPLETED":
        raise RuntimeError(f"Goal não terminou COMPLETED: {goal.id}")
    return completed


def _find_existing_completion(
    database_path: Path,
    *,
    assessment: VerificationResult,
) -> GoalCompletionReceipt | None:
    with sqlite3.connect(database_path) as connection:
        return _find_existing_completion_in_connection(connection, assessment=assessment)


def _find_existing_completion_in_connection(
    connection: sqlite3.Connection,
    *,
    assessment: VerificationResult,
) -> GoalCompletionReceipt | None:
    results = list_verification_results_in_connection(
        connection,
        subject_type="GOAL",
        subject_id=assessment.subject_id,
    )
    verification: VerificationResult | None = None
    for result in reversed(results):
        if result.status != "VERIFIED":
            continue
        if result.observed.get("verification_type") != CONFIRMATION_TYPE:
            continue
        if result.observed.get("confirmed_assessment_id") != assessment.id:
            continue
        verification = result
        break
    if verification is None:
        return None

    confirmation_event_id = verification.observed.get("confirmation_event_id")
    if not isinstance(confirmation_event_id, str) or not confirmation_event_id.strip():
        raise TypeError("goal verification possui confirmation_event_id inválido")

    row = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'goal.completed' AND goal_id = ?
        ORDER BY occurred_at DESC, id DESC
        """,
        (assessment.subject_id,),
    ).fetchall()
    completion_event_id: str | None = None
    for event_id, raw_payload in row:
        payload = json.loads(str(raw_payload))
        if not isinstance(payload, dict):
            raise TypeError("payload de goal.completed inválido")
        if payload.get("goal_verification_id") == verification.id:
            completion_event_id = str(event_id)
            break
    if completion_event_id is None:
        return None

    goal = _goal_in_connection(connection, assessment.subject_id)
    if goal.status != "COMPLETED":
        return None
    return GoalCompletionReceipt(
        assessment=assessment,
        verification=verification,
        goal=goal,
        confirmation_event_id=confirmation_event_id,
        completion_event_id=completion_event_id,
        created=False,
    )


def _goal_from_row(row: tuple[object, ...]) -> Goal:
    return Goal(
        id=str(row[0]),
        title=str(row[1]),
        origin=str(row[2]),
        parent_goal_id=str(row[3]) if row[3] is not None else None,
        desired_state=json.loads(str(row[4])),
        success_criteria=tuple(json.loads(str(row[5]))),
        status=str(row[6]),
        created_at=datetime.fromisoformat(str(row[7])),
        updated_at=datetime.fromisoformat(str(row[8])),
    )


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
