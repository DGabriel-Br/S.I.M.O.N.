import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

OPEN_STATUSES = {"ACTIVE", "SUSPENDED"}
OUTCOMES = {"SUCCESS", "FAILURE", "PARTIAL", "INCONCLUSIVE", "INTERRUPTED"}
GOAL_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


@dataclass(frozen=True, slots=True)
class Experience:
    id: str
    title: str
    goal_id: str | None
    parent_experience_id: str | None
    status: str
    outcome: str | None
    event_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    verification_ids: tuple[str, ...]
    summary: str | None
    started_at: datetime
    ended_at: datetime | None
    updated_at: datetime


def _experience_from_row(row: tuple[object, ...]) -> Experience:
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


def _validate_goal(connection: sqlite3.Connection, goal_id: str | None) -> None:
    if goal_id is None:
        return

    row = connection.execute(
        "SELECT status FROM goals WHERE id = ?",
        (goal_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if str(row[0]) in GOAL_TERMINAL_STATUSES:
        raise ValueError(f"experience exige goal aberto: {goal_id}")


def _validate_parent(
    connection: sqlite3.Connection,
    parent_experience_id: str | None,
) -> None:
    if parent_experience_id is None:
        return

    row = connection.execute(
        "SELECT id FROM experiences WHERE id = ?",
        (parent_experience_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"experience pai não encontrada: {parent_experience_id}")


def create_experience(
    database_path: Path,
    *,
    title: str,
    goal_id: str | None = None,
    parent_experience_id: str | None = None,
) -> Experience:
    if not title.strip():
        raise ValueError("experience precisa de um título")

    now = datetime.now(UTC)
    experience = Experience(
        id=f"exp_{uuid4().hex}",
        title=title.strip(),
        goal_id=goal_id,
        parent_experience_id=parent_experience_id,
        status="ACTIVE",
        outcome=None,
        event_ids=(),
        action_ids=(),
        verification_ids=(),
        summary=None,
        started_at=now,
        ended_at=None,
        updated_at=now,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _validate_goal(connection, goal_id)
        _validate_parent(connection, parent_experience_id)
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
                experience.parent_experience_id,
                experience.status,
                None,
                "[]",
                "[]",
                "[]",
                None,
                experience.started_at.isoformat(),
                None,
                experience.updated_at.isoformat(),
            ),
        )

    return experience


def get_experience(database_path: Path, experience_id: str) -> Experience | None:
    with sqlite3.connect(database_path) as connection:
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

    return _experience_from_row(row) if row is not None else None


def get_latest_experience(
    database_path: Path,
    *,
    goal_id: str | None = None,
) -> Experience | None:
    where = "" if goal_id is None else " WHERE goal_id = ?"
    parameters: tuple[object, ...] = () if goal_id is None else (goal_id,)
    with sqlite3.connect(database_path) as connection:
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
            """
            + where
            + " ORDER BY updated_at DESC, id DESC LIMIT 1",
            parameters,
        ).fetchone()

    return _experience_from_row(row) if row is not None else None


def list_open_experiences(database_path: Path) -> tuple[Experience, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
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
            WHERE status IN ('ACTIVE', 'SUSPENDED')
            ORDER BY started_at, id
            """
        ).fetchall()

    return tuple(_experience_from_row(row) for row in rows)


def _get_experience_context(
    connection: sqlite3.Connection,
    experience_id: str,
) -> tuple[str | None, str]:
    row = connection.execute(
        "SELECT goal_id, status FROM experiences WHERE id = ?",
        (experience_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"experience não encontrada: {experience_id}")

    return (str(row[0]) if row[0] is not None else None, str(row[1]))


def _append_reference(
    database_path: Path,
    *,
    experience_id: str,
    reference_id: str,
    column: str,
    reference_kind: str,
) -> Experience:
    if column not in {"event_ids_json", "action_ids_json", "verification_ids_json"}:
        raise ValueError(f"coluna de referência inválida: {column}")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        experience_goal_id, experience_status = _get_experience_context(
            connection, experience_id
        )
        if reference_kind == "ACTION" and experience_status == "CLOSED":
            raise ValueError("experience fechada não aceita novas actions")

        if reference_kind == "EVENT":
            row = connection.execute(
                "SELECT goal_id, experience_id FROM events WHERE id = ?",
                (reference_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"event não encontrado: {reference_id}")
            reference_goal_id = str(row[0]) if row[0] is not None else None
            event_experience_id = str(row[1]) if row[1] is not None else None
            if event_experience_id is not None and event_experience_id != experience_id:
                raise ValueError("event já pertence a outra experience")
        elif reference_kind == "ACTION":
            row = connection.execute(
                "SELECT goal_id FROM actions WHERE id = ?",
                (reference_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"action não encontrada: {reference_id}")
            reference_goal_id = str(row[0])
        else:
            row = connection.execute(
                "SELECT subject_type, subject_id FROM verification_results WHERE id = ?",
                (reference_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"verification não encontrada: {reference_id}")

            subject_type = str(row[0])
            subject_id = str(row[1])
            if subject_type == "GOAL":
                reference_goal_id = subject_id
            else:
                action_row = connection.execute(
                    "SELECT goal_id FROM actions WHERE id = ?",
                    (subject_id,),
                ).fetchone()
                if action_row is None:
                    raise ValueError(f"action da verification não encontrada: {subject_id}")
                reference_goal_id = str(action_row[0])

        if (
            experience_goal_id is not None
            and reference_goal_id is not None
            and reference_goal_id != experience_goal_id
        ):
            raise ValueError(f"{reference_kind.lower()} não pertence ao goal da experience")

        current_row = connection.execute(
            f"SELECT {column} FROM experiences WHERE id = ?",
            (experience_id,),
        ).fetchone()
        if current_row is None:
            raise RuntimeError(f"experience desapareceu durante atualização: {experience_id}")

        references = list(json.loads(str(current_row[0])))
        if reference_id not in references:
            references.append(reference_id)
            connection.execute(
                f"UPDATE experiences SET {column} = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(references, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                    experience_id,
                ),
            )

    updated = get_experience(database_path, experience_id)
    if updated is None:
        raise RuntimeError(f"experience desapareceu após atualização: {experience_id}")
    return updated


def add_event_to_experience(
    database_path: Path,
    experience_id: str,
    event_id: str,
) -> Experience:
    return _append_reference(
        database_path,
        experience_id=experience_id,
        reference_id=event_id,
        column="event_ids_json",
        reference_kind="EVENT",
    )


def add_action_to_experience(
    database_path: Path,
    experience_id: str,
    action_id: str,
) -> Experience:
    return _append_reference(
        database_path,
        experience_id=experience_id,
        reference_id=action_id,
        column="action_ids_json",
        reference_kind="ACTION",
    )


def add_verification_to_experience(
    database_path: Path,
    experience_id: str,
    verification_id: str,
) -> Experience:
    return _append_reference(
        database_path,
        experience_id=experience_id,
        reference_id=verification_id,
        column="verification_ids_json",
        reference_kind="VERIFICATION",
    )


def suspend_experience(database_path: Path, experience_id: str) -> Experience:
    return _transition_open_experience(database_path, experience_id, "SUSPENDED")


def resume_experience(database_path: Path, experience_id: str) -> Experience:
    current = get_experience(database_path, experience_id)
    if current is None:
        raise ValueError(f"experience não encontrada: {experience_id}")
    if current.status != "SUSPENDED":
        raise ValueError(f"experience não está suspensa: {experience_id}")

    return _transition_open_experience(database_path, experience_id, "ACTIVE")


def _transition_open_experience(
    database_path: Path,
    experience_id: str,
    new_status: str,
) -> Experience:
    current = get_experience(database_path, experience_id)
    if current is None:
        raise ValueError(f"experience não encontrada: {experience_id}")

    allowed = {
        "ACTIVE": {"SUSPENDED"},
        "SUSPENDED": {"ACTIVE"},
    }.get(current.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"transição de experience inválida: {current.status} -> {new_status}"
        )

    now = datetime.now(UTC)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE experiences
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, now.isoformat(), experience_id, current.status),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"experience mudou durante a transição: {experience_id}")

    updated = get_experience(database_path, experience_id)
    if updated is None:
        raise RuntimeError(f"experience desapareceu após atualização: {experience_id}")
    return updated


def close_experience(
    database_path: Path,
    experience_id: str,
    *,
    outcome: str,
    summary: str | None = None,
) -> Experience:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome de experience inválido: {outcome}")

    current = get_experience(database_path, experience_id)
    if current is None:
        raise ValueError(f"experience não encontrada: {experience_id}")
    if current.status not in OPEN_STATUSES:
        raise ValueError(f"experience já está fechada: {experience_id}")

    now = datetime.now(UTC)
    normalized_summary = summary.strip() if summary is not None and summary.strip() else None
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE experiences
            SET
                status = 'CLOSED',
                outcome = ?,
                summary = ?,
                ended_at = ?,
                updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                outcome,
                normalized_summary,
                now.isoformat(),
                now.isoformat(),
                experience_id,
                current.status,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"experience mudou durante o fechamento: {experience_id}")

    updated = get_experience(database_path, experience_id)
    if updated is None:
        raise RuntimeError(f"experience desapareceu após fechamento: {experience_id}")
    return updated


def suspend_active_experiences(database_path: Path) -> tuple[Experience, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id FROM experiences WHERE status = 'ACTIVE' ORDER BY started_at, id"
        ).fetchall()

    suspended: list[Experience] = []
    for row in rows:
        suspended.append(suspend_experience(database_path, str(row[0])))

    return tuple(suspended)
