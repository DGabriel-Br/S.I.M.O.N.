from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ACTIVE = "ACTIVE"
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "SUPERSEDED", "CANCELLED"}
ALLOWED_TRANSITIONS = {
    ACTIVE: TERMINAL_STATUSES,
}
GOAL_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    goal_id: str
    revision: int
    steps: tuple[dict[str, object], ...]
    status: str
    created_at: datetime
    updated_at: datetime


def _validate_steps(steps: tuple[dict[str, object], ...]) -> None:
    if not steps:
        raise ValueError("plan precisa de pelo menos um passo")

    known_step_ids: set[str] = set()
    for step in steps:
        step_id = step.get("id")
        description = step.get("description")

        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError("cada passo do plan precisa de um id")
        if step_id in known_step_ids:
            raise ValueError(f"id de passo duplicado no plan: {step_id}")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"passo {step_id} precisa de uma descrição")

        dependencies = step.get("depends_on", ())
        if not isinstance(dependencies, (list, tuple)):
            raise TypeError(f"depends_on inválido no passo {step_id}")
        if any(not isinstance(dependency, str) for dependency in dependencies):
            raise ValueError(f"depends_on inválido no passo {step_id}")

        missing_dependencies = [
            dependency for dependency in dependencies if dependency not in known_step_ids
        ]
        if missing_dependencies:
            raise ValueError(
                f"passo {step_id} depende de passo ainda não definido: "
                f"{', '.join(missing_dependencies)}"
            )

        known_step_ids.add(step_id)


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


def create_plan_in_connection(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    steps: tuple[dict[str, object], ...],
) -> Plan:
    _validate_steps(steps)
    now = datetime.now(UTC)

    goal_row = connection.execute(
        "SELECT status FROM goals WHERE id = ?",
        (goal_id,),
    ).fetchone()
    if goal_row is None:
        raise ValueError(f"goal não encontrado: {goal_id}")

    goal_status = str(goal_row[0])
    if goal_status in GOAL_TERMINAL_STATUSES:
        raise ValueError(f"não é possível criar plan para goal terminal: {goal_status}")

    current_active = connection.execute(
        "SELECT id FROM plans WHERE goal_id = ? AND status = ?",
        (goal_id, ACTIVE),
    ).fetchone()
    if current_active is not None:
        connection.execute(
            """
            UPDATE plans
            SET status = 'SUPERSEDED', updated_at = ?
            WHERE id = ? AND status = 'ACTIVE'
            """,
            (now.isoformat(), str(current_active[0])),
        )

    revision_row = connection.execute(
        "SELECT COALESCE(MAX(revision), 0) + 1 FROM plans WHERE goal_id = ?",
        (goal_id,),
    ).fetchone()
    revision = int(revision_row[0]) if revision_row is not None else 1

    plan = Plan(
        id=f"pln_{uuid4().hex}",
        goal_id=goal_id,
        revision=revision,
        steps=steps,
        status=ACTIVE,
        created_at=now,
        updated_at=now,
    )
    steps_json = json.dumps(steps, ensure_ascii=False, separators=(",", ":"))

    connection.execute(
        """
        INSERT INTO plans (
            id,
            goal_id,
            revision,
            steps_json,
            status,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan.id,
            plan.goal_id,
            plan.revision,
            steps_json,
            plan.status,
            plan.created_at.isoformat(),
            plan.updated_at.isoformat(),
        ),
    )
    return plan


def create_plan(
    database_path: Path,
    *,
    goal_id: str,
    steps: tuple[dict[str, object], ...],
) -> Plan:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return create_plan_in_connection(
            connection,
            goal_id=goal_id,
            steps=steps,
        )

def get_plan(database_path: Path, plan_id: str) -> Plan | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, goal_id, revision, steps_json, status, created_at, updated_at
            FROM plans
            WHERE id = ?
            """,
            (plan_id,),
        ).fetchone()

    return _plan_from_row(row) if row is not None else None


def get_active_plan(database_path: Path, goal_id: str) -> Plan | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, goal_id, revision, steps_json, status, created_at, updated_at
            FROM plans
            WHERE goal_id = ? AND status = 'ACTIVE'
            """,
            (goal_id,),
        ).fetchone()

    return _plan_from_row(row) if row is not None else None


def list_plans_for_goal(database_path: Path, goal_id: str) -> tuple[Plan, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, goal_id, revision, steps_json, status, created_at, updated_at
            FROM plans
            WHERE goal_id = ?
            ORDER BY revision
            """,
            (goal_id,),
        ).fetchall()

    return tuple(_plan_from_row(row) for row in rows)


def transition_plan(database_path: Path, plan_id: str, new_status: str) -> Plan:
    current = get_plan(database_path, plan_id)
    if current is None:
        raise ValueError(f"plan não encontrado: {plan_id}")

    allowed = ALLOWED_TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise ValueError(f"transição de plan inválida: {current.status} -> {new_status}")

    updated_at = datetime.now(UTC)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE plans
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, updated_at.isoformat(), plan_id, current.status),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"plan mudou durante a transição: {plan_id}")

    updated = get_plan(database_path, plan_id)
    if updated is None:
        raise RuntimeError(f"plan desapareceu após atualização: {plan_id}")
    return updated
