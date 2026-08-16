from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SUBJECT_TYPES = {"ACTION", "GOAL"}
STATUSES = {"VERIFIED", "FAILED", "INCONCLUSIVE", "ASSESSED"}
MIN_STRENGTH = 1
MAX_STRENGTH = 5


@dataclass(frozen=True, slots=True)
class VerificationResult:
    id: str
    subject_type: str
    subject_id: str
    criteria: tuple[dict[str, object], ...]
    status: str
    evidence_event_ids: tuple[str, ...]
    observed: dict[str, object]
    strength: int
    created_at: datetime


def _verification_from_row(row: tuple[object, ...]) -> VerificationResult:
    strength = row[7]
    if not isinstance(strength, int):
        raise TypeError("strength inválida no banco")

    return VerificationResult(
        id=str(row[0]),
        subject_type=str(row[1]),
        subject_id=str(row[2]),
        criteria=tuple(json.loads(str(row[3]))),
        status=str(row[4]),
        evidence_event_ids=tuple(json.loads(str(row[5]))),
        observed=json.loads(str(row[6])),
        strength=strength,
        created_at=datetime.fromisoformat(str(row[8])),
    )


def _verification_select() -> str:
    return """
        SELECT
            id,
            subject_type,
            subject_id,
            criteria_json,
            status,
            evidence_event_ids_json,
            observed_json,
            strength,
            created_at
        FROM verification_results
    """


def _validate_subject(
    connection: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: str,
) -> None:
    if subject_type == "ACTION":
        row = connection.execute(
            "SELECT status FROM actions WHERE id = ?",
            (subject_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"action não encontrada: {subject_id}")
        if str(row[0]) in {"PENDING", "RUNNING", "WAITING"}:
            raise ValueError("action precisa estar em estado terminal antes da verificação")
        return

    row = connection.execute(
        "SELECT id FROM goals WHERE id = ?",
        (subject_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"goal não encontrado: {subject_id}")


def _validate_evidence(
    connection: sqlite3.Connection,
    evidence_event_ids: tuple[str, ...],
) -> None:
    if not evidence_event_ids:
        raise ValueError("verification precisa de pelo menos um Event como evidência")

    for event_id in evidence_event_ids:
        row = connection.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Event de evidência não encontrado: {event_id}")


def _validate_input(
    *,
    subject_type: str,
    criteria: tuple[dict[str, object], ...],
    status: str,
    strength: int,
) -> None:
    if subject_type not in SUBJECT_TYPES:
        raise ValueError(f"subject_type inválido: {subject_type}")
    if not criteria:
        raise ValueError("verification precisa de critérios")
    if status not in STATUSES:
        raise ValueError(f"status de verification inválido: {status}")
    if isinstance(strength, bool) or not isinstance(strength, int):
        raise TypeError("strength precisa ser um inteiro")
    if not MIN_STRENGTH <= strength <= MAX_STRENGTH:
        raise ValueError(f"strength precisa estar entre {MIN_STRENGTH} e {MAX_STRENGTH}")


def create_verification_result_in_connection(
    connection: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: str,
    criteria: tuple[dict[str, object], ...],
    status: str,
    evidence_event_ids: tuple[str, ...],
    observed: dict[str, object],
    strength: int,
) -> VerificationResult:
    _validate_input(
        subject_type=subject_type,
        criteria=criteria,
        status=status,
        strength=strength,
    )
    _validate_subject(
        connection,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    _validate_evidence(connection, evidence_event_ids)

    result = VerificationResult(
        id=f"ver_{uuid4().hex}",
        subject_type=subject_type,
        subject_id=subject_id,
        criteria=criteria,
        status=status,
        evidence_event_ids=evidence_event_ids,
        observed=observed,
        strength=strength,
        created_at=datetime.now(UTC),
    )
    connection.execute(
        """
        INSERT INTO verification_results (
            id,
            subject_type,
            subject_id,
            criteria_json,
            status,
            evidence_event_ids_json,
            observed_json,
            strength,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.id,
            result.subject_type,
            result.subject_id,
            json.dumps(result.criteria, ensure_ascii=False, separators=(",", ":")),
            result.status,
            json.dumps(result.evidence_event_ids, separators=(",", ":")),
            json.dumps(result.observed, ensure_ascii=False, separators=(",", ":")),
            result.strength,
            result.created_at.isoformat(),
        ),
    )
    return result


def create_verification_result(
    database_path: Path,
    *,
    subject_type: str,
    subject_id: str,
    criteria: tuple[dict[str, object], ...],
    status: str,
    evidence_event_ids: tuple[str, ...],
    observed: dict[str, object],
    strength: int,
) -> VerificationResult:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return create_verification_result_in_connection(
            connection,
            subject_type=subject_type,
            subject_id=subject_id,
            criteria=criteria,
            status=status,
            evidence_event_ids=evidence_event_ids,
            observed=observed,
            strength=strength,
        )


def get_verification_result_in_connection(
    connection: sqlite3.Connection,
    verification_id: str,
) -> VerificationResult | None:
    row = connection.execute(
        _verification_select() + " WHERE id = ?",
        (verification_id,),
    ).fetchone()
    return _verification_from_row(row) if row is not None else None


def get_verification_result(
    database_path: Path,
    verification_id: str,
) -> VerificationResult | None:
    with sqlite3.connect(database_path) as connection:
        return get_verification_result_in_connection(connection, verification_id)


def list_verification_results_in_connection(
    connection: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: str,
) -> tuple[VerificationResult, ...]:
    if subject_type not in SUBJECT_TYPES:
        raise ValueError(f"subject_type inválido: {subject_type}")

    rows = connection.execute(
        _verification_select()
        + " WHERE subject_type = ? AND subject_id = ? ORDER BY created_at, id",
        (subject_type, subject_id),
    ).fetchall()
    return tuple(_verification_from_row(row) for row in rows)


def list_verification_results(
    database_path: Path,
    *,
    subject_type: str,
    subject_id: str,
) -> tuple[VerificationResult, ...]:
    with sqlite3.connect(database_path) as connection:
        return list_verification_results_in_connection(
            connection,
            subject_type=subject_type,
            subject_id=subject_id,
        )
