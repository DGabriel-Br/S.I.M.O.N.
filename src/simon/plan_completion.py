from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from simon.events import Event
from simon.goals import get_goal
from simon.plans import Plan, get_active_plan, transition_plan_in_connection
from simon.step_readiness import evaluate_active_plan


@dataclass(frozen=True, slots=True)
class PlanCompletionReceipt:
    plan: Plan
    completion_event_id: str
    verified_step_ids: tuple[str, ...]
    created: bool


def complete_verified_plan(
    database_path: Path,
    *,
    goal_id: str,
    trace_id: str | None = None,
) -> PlanCompletionReceipt:
    goal = get_goal(database_path, goal_id)
    if goal is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if goal.status != "ACTIVE":
        raise ValueError(f"conclusão de plan exige goal ACTIVE: {goal.status}")

    active_plan = get_active_plan(database_path, goal_id)
    if active_plan is None:
        existing = _find_existing_completion(database_path, goal_id=goal_id)
        if existing is not None:
            return existing
        raise ValueError(f"goal não possui plan ACTIVE: {goal_id}")

    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    not_verified = tuple(
        f"{step.step_id}={step.state}" for step in readiness.steps if step.state != "VERIFIED"
    )
    if not_verified:
        raise ValueError(
            "plan ainda possui steps não verificados: " + ", ".join(not_verified)
        )

    completion_trace_id = trace_id or f"trc_{uuid4().hex}"
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        current_plan_row = connection.execute(
            """
            SELECT id, status
            FROM plans
            WHERE goal_id = ? AND status = 'ACTIVE'
            """,
            (goal_id,),
        ).fetchone()
        if current_plan_row is None:
            existing = _find_existing_completion_in_connection(connection, goal_id=goal_id)
            if existing is not None:
                return existing
            raise RuntimeError(f"plan ACTIVE desapareceu durante conclusão: {active_plan.id}")
        if str(current_plan_row[0]) != active_plan.id:
            raise RuntimeError(
                "plan ACTIVE mudou durante conclusão: "
                f"{active_plan.id} -> {current_plan_row[0]}"
            )

        goal_row = connection.execute(
            "SELECT status FROM goals WHERE id = ?",
            (goal_id,),
        ).fetchone()
        if goal_row is None:
            raise ValueError(f"goal não encontrado: {goal_id}")
        if str(goal_row[0]) != "ACTIVE":
            raise RuntimeError(f"goal mudou durante conclusão do plan: {goal_row[0]}")

        verified_pairs = _verified_steps_in_connection(connection, active_plan)
        if len(verified_pairs) != len(active_plan.steps):
            verified_step_ids = {step_id for step_id, _ in verified_pairs}
            missing = [
                _step_id(step)
                for step in active_plan.steps
                if _step_id(step) not in verified_step_ids
            ]
            raise RuntimeError(
                "evidência de verification mudou durante conclusão do plan: "
                + ", ".join(missing)
            )

        completed = transition_plan_in_connection(connection, active_plan.id, "COMPLETED")
        event = Event.create(
            kind="plan.completed",
            source="system",
            payload={
                "plan_id": completed.id,
                "plan_revision": completed.revision,
                "verified_step_ids": [step_id for step_id, _ in verified_pairs],
                "verified_action_ids": [action_id for _, action_id in verified_pairs],
                "goal_status_after_completion": "ACTIVE",
            },
            trace_id=completion_trace_id,
            goal_id=goal_id,
        )
        _insert_event(connection, event)

    return PlanCompletionReceipt(
        plan=completed,
        completion_event_id=event.id,
        verified_step_ids=tuple(step_id for step_id, _ in verified_pairs),
        created=True,
    )


def _verified_steps_in_connection(
    connection: sqlite3.Connection,
    plan: Plan,
) -> tuple[tuple[str, str], ...]:
    verified: list[tuple[str, str]] = []
    for step in plan.steps:
        step_id = _step_id(step)
        row = connection.execute(
            """
            SELECT a.id
            FROM actions AS a
            JOIN verification_results AS v
              ON v.subject_type = 'ACTION'
             AND v.subject_id = a.id
             AND v.status = 'VERIFIED'
            WHERE a.plan_id = ?
              AND a.step_id = ?
              AND a.status = 'COMPLETED'
            ORDER BY a.created_at DESC, a.id DESC, v.created_at DESC, v.id DESC
            LIMIT 1
            """,
            (plan.id, step_id),
        ).fetchone()
        if row is not None:
            verified.append((step_id, str(row[0])))
    return tuple(verified)


def _find_existing_completion(
    database_path: Path,
    *,
    goal_id: str,
) -> PlanCompletionReceipt | None:
    with sqlite3.connect(database_path) as connection:
        return _find_existing_completion_in_connection(connection, goal_id=goal_id)


def _find_existing_completion_in_connection(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
) -> PlanCompletionReceipt | None:
    row = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'plan.completed' AND goal_id = ?
        ORDER BY occurred_at DESC, id DESC
        LIMIT 1
        """,
        (goal_id,),
    ).fetchone()
    if row is None:
        return None

    payload = json.loads(str(row[1]))
    if not isinstance(payload, dict):
        raise TypeError("payload de plan.completed inválido")
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise TypeError("plan.completed possui plan_id inválido")

    plan_row = connection.execute(
        """
        SELECT id, goal_id, revision, steps_json, status, created_at, updated_at
        FROM plans
        WHERE id = ?
        """,
        (plan_id,),
    ).fetchone()
    if plan_row is None:
        raise RuntimeError(f"plan referenciado por plan.completed não existe: {plan_id}")

    plan = _plan_from_row(plan_row)
    if plan.status != "COMPLETED":
        return None

    raw_step_ids = payload.get("verified_step_ids", [])
    if not isinstance(raw_step_ids, list) or any(
        not isinstance(step_id, str) for step_id in raw_step_ids
    ):
        raise TypeError("plan.completed possui verified_step_ids inválido")

    return PlanCompletionReceipt(
        plan=plan,
        completion_event_id=str(row[0]),
        verified_step_ids=tuple(raw_step_ids),
        created=False,
    )


def _plan_from_row(row: tuple[object, ...]) -> Plan:
    revision = row[2]
    if not isinstance(revision, int):
        raise TypeError("revision inválida no banco")
    return Plan(
        id=str(row[0]),
        goal_id=str(row[1]),
        revision=revision,
        steps=tuple(json.loads(str(row[3]))),
        status=str(row[4]),
        created_at=datetime.fromisoformat(str(row[5])),
        updated_at=datetime.fromisoformat(str(row[6])),
    )


def _step_id(step: dict[str, object]) -> str:
    value = step.get("id")
    if not isinstance(value, str):
        raise TypeError("step persistido possui id com tipo inválido")
    normalized = value.strip()
    if not normalized:
        raise ValueError("step persistido possui id vazio")
    return normalized


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
