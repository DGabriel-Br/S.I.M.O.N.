import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ORIGINS = {"USER", "SYSTEM", "DERIVED", "MAINTENANCE", "LAB"}
OPEN_STATUSES = {"ACTIVE", "WAITING", "BLOCKED", "PAUSED"}
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}
ALLOWED_TRANSITIONS = {
    "ACTIVE": {"WAITING", "BLOCKED", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"},
    "WAITING": {"ACTIVE", "CANCELLED"},
    "BLOCKED": {"ACTIVE", "CANCELLED"},
    "PAUSED": {"ACTIVE", "CANCELLED"},
}


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    title: str
    origin: str
    parent_goal_id: str | None
    desired_state: dict[str, object]
    success_criteria: tuple[dict[str, object], ...]
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        title: str,
        origin: str,
        desired_state: dict[str, object],
        success_criteria: tuple[dict[str, object], ...],
        parent_goal_id: str | None = None,
    ) -> Goal:
        if not title.strip():
            raise ValueError("goal precisa de um título")
        if origin not in ORIGINS:
            raise ValueError(f"origem de goal inválida: {origin}")
        if not desired_state:
            raise ValueError("goal precisa de um estado desejado")
        if not success_criteria:
            raise ValueError("goal precisa de critérios de sucesso")

        now = datetime.now(UTC)
        return cls(
            id=f"gol_{uuid4().hex}",
            title=title.strip(),
            origin=origin,
            parent_goal_id=parent_goal_id,
            desired_state=desired_state,
            success_criteria=success_criteria,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
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


def insert_goal(database_path: Path, goal: Goal) -> None:
    desired_state_json = json.dumps(
        goal.desired_state,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    success_criteria_json = json.dumps(
        goal.success_criteria,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO goals (
                id,
                title,
                origin,
                parent_goal_id,
                desired_state_json,
                success_criteria_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                goal.id,
                goal.title,
                goal.origin,
                goal.parent_goal_id,
                desired_state_json,
                success_criteria_json,
                goal.status,
                goal.created_at.isoformat(),
                goal.updated_at.isoformat(),
            ),
        )


def get_goal(database_path: Path, goal_id: str) -> Goal | None:
    with sqlite3.connect(database_path) as connection:
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

    return _goal_from_row(row) if row is not None else None


def list_open_goals(database_path: Path) -> tuple[Goal, ...]:
    placeholders = ",".join("?" for _ in OPEN_STATUSES)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
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
            WHERE status IN ({placeholders})
            ORDER BY created_at, id
            """,
            tuple(sorted(OPEN_STATUSES)),
        ).fetchall()

    return tuple(_goal_from_row(row) for row in rows)


def transition_goal(database_path: Path, goal_id: str, new_status: str) -> Goal:
    current = get_goal(database_path, goal_id)
    if current is None:
        raise ValueError(f"goal não encontrado: {goal_id}")

    allowed = ALLOWED_TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise ValueError(f"transição de goal inválida: {current.status} -> {new_status}")

    updated_at = datetime.now(UTC)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE goals
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, updated_at.isoformat(), goal_id, current.status),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(f"goal mudou durante a transição: {goal_id}")

    updated = get_goal(database_path, goal_id)
    if updated is None:
        raise RuntimeError(f"goal desapareceu após atualização: {goal_id}")
    return updated
