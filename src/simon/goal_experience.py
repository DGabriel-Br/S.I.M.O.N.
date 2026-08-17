from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from simon.events import Event
from simon.experiences import Experience

CLOSURE_EVENT_KIND = "experience.goal_cycle.closed"


@dataclass(frozen=True, slots=True)
class GoalExperienceClosure:
    experience: Experience
    closure_event_id: str
    created: bool


def ensure_completed_goal_experience_in_connection(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    goal_verification_id: str,
    goal_completion_event_id: str,
    trace_id: str,
) -> GoalExperienceClosure:
    existing = _find_existing_closure(
        connection,
        goal_id=goal_id,
        goal_verification_id=goal_verification_id,
    )
    if existing is not None:
        return existing

    goal_row = connection.execute(
        """
        SELECT title, status, created_at
        FROM goals
        WHERE id = ?
        """,
        (goal_id,),
    ).fetchone()
    if goal_row is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if str(goal_row[1]) != "COMPLETED":
        raise ValueError("Experience final exige Goal COMPLETED")

    verification_row = connection.execute(
        """
        SELECT subject_type, subject_id, status, observed_json
        FROM verification_results
        WHERE id = ?
        """,
        (goal_verification_id,),
    ).fetchone()
    if verification_row is None:
        raise ValueError(f"Verification final do Goal não encontrada: {goal_verification_id}")
    if (
        str(verification_row[0]) != "GOAL"
        or str(verification_row[1]) != goal_id
        or str(verification_row[2]) != "VERIFIED"
    ):
        raise ValueError("Experience final exige Verification VERIFIED do próprio Goal")
    verification_observed = json.loads(str(verification_row[3]))
    if not isinstance(verification_observed, dict):
        raise TypeError("observed da Verification final do Goal inválido")
    if verification_observed.get("verification_type") != "goal.assessment_confirmation":
        raise ValueError("Verification final não representa confirmação do assessment do Goal")

    completion_row = connection.execute(
        """
        SELECT occurred_at, kind, source
        FROM events
        WHERE id = ? AND goal_id = ?
        """,
        (goal_completion_event_id, goal_id),
    ).fetchone()
    if completion_row is None:
        raise ValueError(f"Event goal.completed não encontrado: {goal_completion_event_id}")
    if str(completion_row[1]) != "goal.completed" or str(completion_row[2]) != "system":
        raise ValueError("Experience final exige Event goal.completed do system")

    plans = _plan_lineage(connection, goal_id=goal_id)
    action_ids = _action_ids(connection, goal_id=goal_id)
    verification_rows = _verification_rows(connection, goal_id=goal_id)
    verification_ids = tuple(str(row[0]) for row in verification_rows)
    if goal_verification_id not in verification_ids:
        raise RuntimeError("Verification final do Goal ficou fora da Experience")
    event_ids = _causal_event_ids(
        connection,
        goal_id=goal_id,
        verification_rows=verification_rows,
        goal_completion_event_id=goal_completion_event_id,
    )

    started_at = datetime.fromisoformat(str(goal_row[2]))
    ended_at = datetime.fromisoformat(str(completion_row[0]))
    experience_id = f"exp_{uuid4().hex}"
    summary = _summary(
        title=str(goal_row[0]),
        plan_count=len(plans),
        action_count=len(action_ids),
        verification_count=len(verification_ids),
    )
    closure_event = Event.create(
        kind=CLOSURE_EVENT_KIND,
        source="system",
        payload={
            "experience_id": experience_id,
            "goal_id": goal_id,
            "goal_verification_id": goal_verification_id,
            "goal_completion_event_id": goal_completion_event_id,
            "outcome": "SUCCESS",
            "plans": [
                {"plan_id": plan_id, "revision": revision, "status": status}
                for plan_id, revision, status in plans
            ],
            "action_ids": list(action_ids),
            "verification_ids": list(verification_ids),
            "causal_event_ids": list(event_ids),
        },
        trace_id=trace_id,
        goal_id=goal_id,
        experience_id=experience_id,
    )
    final_event_ids = tuple(dict.fromkeys((*event_ids, closure_event.id)))
    experience = Experience(
        id=experience_id,
        title=str(goal_row[0]),
        goal_id=goal_id,
        parent_experience_id=None,
        status="CLOSED",
        outcome="SUCCESS",
        event_ids=final_event_ids,
        action_ids=action_ids,
        verification_ids=verification_ids,
        summary=summary,
        started_at=started_at,
        ended_at=ended_at,
        updated_at=ended_at,
    )

    connection.execute(
        """
        INSERT INTO experiences (
            id,
            title,
            goal_id,
            parent_experience_id,
            status,
            outcome,
            event_ids_json,
            action_ids_json,
            verification_ids_json,
            summary,
            started_at,
            ended_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            experience.id,
            experience.title,
            experience.goal_id,
            None,
            experience.status,
            experience.outcome,
            json.dumps(experience.event_ids, separators=(",", ":")),
            json.dumps(experience.action_ids, separators=(",", ":")),
            json.dumps(experience.verification_ids, separators=(",", ":")),
            experience.summary,
            experience.started_at.isoformat(),
            experience.ended_at.isoformat() if experience.ended_at is not None else None,
            experience.updated_at.isoformat(),
        ),
    )
    _insert_event(connection, closure_event)
    return GoalExperienceClosure(
        experience=experience,
        closure_event_id=closure_event.id,
        created=True,
    )


def _find_existing_closure(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    goal_verification_id: str,
) -> GoalExperienceClosure | None:
    rows = connection.execute(
        """
        SELECT id, payload_json, experience_id
        FROM events
        WHERE kind = ? AND goal_id = ?
        ORDER BY occurred_at DESC, id DESC
        """,
        (CLOSURE_EVENT_KIND, goal_id),
    ).fetchall()
    for event_id, raw_payload, experience_id in rows:
        payload = json.loads(str(raw_payload))
        if not isinstance(payload, dict):
            raise TypeError("payload de experience.goal_cycle.closed inválido")
        if payload.get("goal_verification_id") != goal_verification_id:
            continue
        if not isinstance(experience_id, str) or not experience_id.strip():
            raise TypeError("Event de fechamento possui experience_id inválido")
        experience = _experience_in_connection(connection, experience_id)
        if experience is None:
            raise RuntimeError(
                "Event de fechamento referencia Experience ausente: " + experience_id
            )
        if (
            experience.goal_id != goal_id
            or experience.status != "CLOSED"
            or experience.outcome != "SUCCESS"
        ):
            raise RuntimeError("Experience de fechamento não corresponde ao Goal concluído")
        return GoalExperienceClosure(
            experience=experience,
            closure_event_id=str(event_id),
            created=False,
        )
    return None


def _experience_in_connection(
    connection: sqlite3.Connection,
    experience_id: str,
) -> Experience | None:
    row = connection.execute(
        """
        SELECT
            id,
            title,
            goal_id,
            parent_experience_id,
            status,
            outcome,
            event_ids_json,
            action_ids_json,
            verification_ids_json,
            summary,
            started_at,
            ended_at,
            updated_at
        FROM experiences
        WHERE id = ?
        """,
        (experience_id,),
    ).fetchone()
    if row is None:
        return None
    return Experience(
        id=str(row[0]),
        title=str(row[1]),
        goal_id=str(row[2]) if row[2] is not None else None,
        parent_experience_id=str(row[3]) if row[3] is not None else None,
        status=str(row[4]),
        outcome=str(row[5]) if row[5] is not None else None,
        event_ids=tuple(json.loads(str(row[6]))),
        action_ids=tuple(json.loads(str(row[7]))),
        verification_ids=tuple(json.loads(str(row[8]))),
        summary=str(row[9]) if row[9] is not None else None,
        started_at=datetime.fromisoformat(str(row[10])),
        ended_at=datetime.fromisoformat(str(row[11])) if row[11] is not None else None,
        updated_at=datetime.fromisoformat(str(row[12])),
    )


def _plan_lineage(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
) -> tuple[tuple[str, int, str], ...]:
    rows = connection.execute(
        """
        SELECT id, revision, status
        FROM plans
        WHERE goal_id = ?
        ORDER BY revision, created_at, id
        """,
        (goal_id,),
    ).fetchall()
    lineage: list[tuple[str, int, str]] = []
    for plan_id, revision, status in rows:
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise TypeError("revision inválida ao consolidar Experience")
        lineage.append((str(plan_id), revision, str(status)))
    return tuple(lineage)


def _action_ids(connection: sqlite3.Connection, *, goal_id: str) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE goal_id = ?
        ORDER BY created_at, id
        """,
        (goal_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _verification_rows(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
) -> tuple[tuple[object, ...], ...]:
    rows = connection.execute(
        """
        SELECT v.id, v.evidence_event_ids_json, v.created_at
        FROM verification_results AS v
        LEFT JOIN actions AS a
          ON v.subject_type = 'ACTION'
         AND v.subject_id = a.id
        WHERE (v.subject_type = 'GOAL' AND v.subject_id = ?)
           OR (v.subject_type = 'ACTION' AND a.goal_id = ?)
        ORDER BY v.created_at, v.id
        """,
        (goal_id, goal_id),
    ).fetchall()
    return tuple(rows)


def _causal_event_ids(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    verification_rows: tuple[tuple[object, ...], ...],
    goal_completion_event_id: str,
) -> tuple[str, ...]:
    event_ids: list[str] = []

    acceptance_rows = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'goal.proposal.accepted' AND goal_id = ?
        ORDER BY occurred_at, id
        """,
        (goal_id,),
    ).fetchall()
    for event_id, raw_payload in acceptance_rows:
        payload = _event_payload(raw_payload, kind="goal.proposal.accepted")
        proposal_event_id = payload.get("proposal_event_id")
        if isinstance(proposal_event_id, str) and proposal_event_id.strip():
            event_ids.append(proposal_event_id)
        event_ids.append(str(event_id))

    materialization_rows = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'plan.proposal.materialized' AND goal_id = ?
        ORDER BY occurred_at, id
        """,
        (goal_id,),
    ).fetchall()
    for event_id, raw_payload in materialization_rows:
        payload = _event_payload(raw_payload, kind="plan.proposal.materialized")
        proposal_event_id = payload.get("proposal_event_id")
        if isinstance(proposal_event_id, str) and proposal_event_id.strip():
            event_ids.append(proposal_event_id)
        event_ids.append(str(event_id))

    for _, raw_event_ids, _ in verification_rows:
        parsed = json.loads(str(raw_event_ids))
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise TypeError("Verification possui evidence_event_ids inválido")
        event_ids.extend(parsed)

    event_ids.append(goal_completion_event_id)
    unique_ids = tuple(dict.fromkeys(event_ids))
    _require_events_exist(connection, unique_ids)
    return unique_ids


def _event_payload(raw_payload: object, *, kind: str) -> dict[str, object]:
    payload = json.loads(str(raw_payload))
    if not isinstance(payload, dict):
        raise TypeError(f"payload de {kind} inválido")
    return payload


def _require_events_exist(
    connection: sqlite3.Connection,
    event_ids: tuple[str, ...],
) -> None:
    for event_id in event_ids:
        row = connection.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"Event causal não encontrado ao fechar Experience: {event_id}")


def _summary(
    *,
    title: str,
    plan_count: int,
    action_count: int,
    verification_count: int,
) -> str:
    return (
        f"Goal '{title}' concluído com {plan_count} revisão(ões) de Plan, "
        f"{action_count} Action(s) e {verification_count} VerificationResult(s) registrados."
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
