from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PENDING = "PENDING"
RUNNING = "RUNNING"
WAITING = "WAITING"
TERMINAL_STATUSES = {
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "DENIED",
    "INTERRUPTED",
    "CANCELLED",
}
ALLOWED_TRANSITIONS = {
    PENDING: {RUNNING, WAITING, "BLOCKED", "DENIED", "CANCELLED"},
    RUNNING: {WAITING, "COMPLETED", "FAILED", "BLOCKED", "INTERRUPTED", "CANCELLED"},
    WAITING: {"COMPLETED", "BLOCKED", "CANCELLED"},
}


@dataclass(frozen=True, slots=True)
class Action:
    id: str
    goal_id: str
    plan_id: str
    step_id: str
    kind: str
    input_data: dict[str, object]
    status: str
    reported_result: dict[str, object] | None
    failure: dict[str, object] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


def _action_from_row(row: tuple[object, ...]) -> Action:
    return Action(
        id=str(row[0]),
        goal_id=str(row[1]),
        plan_id=str(row[2]),
        step_id=str(row[3]),
        kind=str(row[4]),
        input_data=json.loads(str(row[5])),
        status=str(row[6]),
        reported_result=json.loads(str(row[7])) if row[7] is not None else None,
        failure=json.loads(str(row[8])) if row[8] is not None else None,
        created_at=datetime.fromisoformat(str(row[9])),
        started_at=datetime.fromisoformat(str(row[10])) if row[10] is not None else None,
        finished_at=datetime.fromisoformat(str(row[11])) if row[11] is not None else None,
        updated_at=datetime.fromisoformat(str(row[12])),
    )


def _action_select() -> str:
    return """
        SELECT
            id,
            goal_id,
            plan_id,
            step_id,
            kind,
            input_json,
            status,
            reported_result_json,
            failure_json,
            created_at,
            started_at,
            finished_at,
            updated_at
        FROM actions
    """


def _validate_target(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    plan_id: str,
    step_id: str,
) -> None:
    goal_row = connection.execute(
        "SELECT status FROM goals WHERE id = ?",
        (goal_id,),
    ).fetchone()
    if goal_row is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if str(goal_row[0]) != "ACTIVE":
        raise ValueError(f"action exige goal ACTIVE: {goal_id}")

    plan_row = connection.execute(
        "SELECT goal_id, steps_json, status FROM plans WHERE id = ?",
        (plan_id,),
    ).fetchone()
    if plan_row is None:
        raise ValueError(f"plan não encontrado: {plan_id}")
    if str(plan_row[0]) != goal_id:
        raise ValueError("plan não pertence ao goal informado")
    if str(plan_row[2]) != "ACTIVE":
        raise ValueError(f"action exige plan ACTIVE: {plan_id}")

    steps = json.loads(str(plan_row[1]))
    step_ids = {
        str(step["id"])
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    }
    if step_id not in step_ids:
        raise ValueError(f"passo não encontrado no plan: {step_id}")


def create_action_in_connection(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    plan_id: str,
    step_id: str,
    kind: str,
    input_data: dict[str, object] | None = None,
) -> Action:
    if not kind.strip():
        raise ValueError("action precisa de um kind")

    now = datetime.now(UTC)
    action = Action(
        id=f"act_{uuid4().hex}",
        goal_id=goal_id,
        plan_id=plan_id,
        step_id=step_id,
        kind=kind.strip(),
        input_data=input_data or {},
        status=PENDING,
        reported_result=None,
        failure=None,
        created_at=now,
        started_at=None,
        finished_at=None,
        updated_at=now,
    )

    _validate_target(
        connection,
        goal_id=goal_id,
        plan_id=plan_id,
        step_id=step_id,
    )
    connection.execute(
        """
        INSERT INTO actions (
            id,
            goal_id,
            plan_id,
            step_id,
            kind,
            input_json,
            status,
            reported_result_json,
            failure_json,
            created_at,
            started_at,
            finished_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action.id,
            action.goal_id,
            action.plan_id,
            action.step_id,
            action.kind,
            json.dumps(action.input_data, ensure_ascii=False, separators=(",", ":")),
            action.status,
            None,
            None,
            action.created_at.isoformat(),
            None,
            None,
            action.updated_at.isoformat(),
        ),
    )
    return action


def create_action(
    database_path: Path,
    *,
    goal_id: str,
    plan_id: str,
    step_id: str,
    kind: str,
    input_data: dict[str, object] | None = None,
) -> Action:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return create_action_in_connection(
            connection,
            goal_id=goal_id,
            plan_id=plan_id,
            step_id=step_id,
            kind=kind,
            input_data=input_data,
        )


def get_action_in_connection(
    connection: sqlite3.Connection,
    action_id: str,
) -> Action | None:
    row = connection.execute(
        _action_select() + " WHERE id = ?",
        (action_id,),
    ).fetchone()
    return _action_from_row(row) if row is not None else None


def get_action(database_path: Path, action_id: str) -> Action | None:
    with sqlite3.connect(database_path) as connection:
        return get_action_in_connection(connection, action_id)


def get_latest_action_for_step_in_connection(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    step_id: str,
) -> Action | None:
    row = connection.execute(
        _action_select()
        + " WHERE plan_id = ? AND step_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (plan_id, step_id),
    ).fetchone()
    return _action_from_row(row) if row is not None else None


def list_actions_for_plan(database_path: Path, plan_id: str) -> tuple[Action, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            _action_select() + " WHERE plan_id = ? ORDER BY created_at, id",
            (plan_id,),
        ).fetchall()

    return tuple(_action_from_row(row) for row in rows)


def transition_action_in_connection(
    connection: sqlite3.Connection,
    action_id: str,
    new_status: str,
    *,
    reported_result: dict[str, object] | None = None,
    failure: dict[str, object] | None = None,
) -> Action:
    current = get_action_in_connection(connection, action_id)
    if current is None:
        raise ValueError(f"action não encontrada: {action_id}")

    allowed = ALLOWED_TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise ValueError(f"transição de action inválida: {current.status} -> {new_status}")

    now = datetime.now(UTC)
    started_at = current.started_at
    finished_at = current.finished_at

    if new_status in {RUNNING, WAITING} and started_at is None:
        started_at = now
    if new_status in TERMINAL_STATUSES:
        finished_at = now

    cursor = connection.execute(
        """
        UPDATE actions
        SET
            status = ?,
            reported_result_json = ?,
            failure_json = ?,
            started_at = ?,
            finished_at = ?,
            updated_at = ?
        WHERE id = ? AND status = ?
        """,
        (
            new_status,
            (
                json.dumps(reported_result, ensure_ascii=False, separators=(",", ":"))
                if reported_result is not None
                else None
            ),
            (
                json.dumps(failure, ensure_ascii=False, separators=(",", ":"))
                if failure is not None
                else None
            ),
            started_at.isoformat() if started_at is not None else None,
            finished_at.isoformat() if finished_at is not None else None,
            now.isoformat(),
            action_id,
            current.status,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"action mudou durante a transição: {action_id}")

    updated = get_action_in_connection(connection, action_id)
    if updated is None:
        raise RuntimeError(f"action desapareceu após atualização: {action_id}")
    return updated


def transition_action(
    database_path: Path,
    action_id: str,
    new_status: str,
    *,
    reported_result: dict[str, object] | None = None,
    failure: dict[str, object] | None = None,
) -> Action:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return transition_action_in_connection(
            connection,
            action_id,
            new_status,
            reported_result=reported_result,
            failure=failure,
        )


def interrupt_running_actions(database_path: Path) -> tuple[Action, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id FROM actions WHERE status = 'RUNNING' ORDER BY created_at, id"
        ).fetchall()

    interrupted: list[Action] = []
    for row in rows:
        action_id = str(row[0])
        interrupted.append(
            transition_action(
                database_path,
                action_id,
                "INTERRUPTED",
                failure={
                    "kind": "runtime_restart",
                    "message": (
                        "execução perdeu continuidade antes de um resultado terminal confiável"
                    ),
                },
            )
        )

    return tuple(interrupted)
