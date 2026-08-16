import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ACTIVE = "ACTIVE"
TERMINAL_STATUSES = {"SUPERSEDED", "RETRACTED", "EXPIRED"}


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    subject_id: str
    predicate: str
    value: object
    epistemic_status: str
    valid_from: datetime | None
    valid_until: datetime | None
    learned_at: datetime
    evidence_event_ids: tuple[str, ...]
    status: str

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        predicate: str,
        value: object,
        epistemic_status: str,
        evidence_event_ids: tuple[str, ...] = (),
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> Claim:
        return cls(
            id=f"clm_{uuid4().hex}",
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            epistemic_status=epistemic_status,
            valid_from=valid_from,
            valid_until=valid_until,
            learned_at=datetime.now(UTC),
            evidence_event_ids=evidence_event_ids,
            status=ACTIVE,
        )


def _claim_from_row(row: tuple[object, ...]) -> Claim:
    return Claim(
        id=str(row[0]),
        subject_id=str(row[1]),
        predicate=str(row[2]),
        value=json.loads(str(row[3])),
        epistemic_status=str(row[4]),
        valid_from=datetime.fromisoformat(str(row[5])) if row[5] is not None else None,
        valid_until=datetime.fromisoformat(str(row[6])) if row[6] is not None else None,
        learned_at=datetime.fromisoformat(str(row[7])),
        evidence_event_ids=tuple(json.loads(str(row[8]))),
        status=str(row[9]),
    )


def insert_claim(database_path: Path, claim: Claim) -> None:
    value_json = json.dumps(claim.value, ensure_ascii=False, separators=(",", ":"))
    evidence_json = json.dumps(claim.evidence_event_ids, separators=(",", ":"))

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO claims (
                id,
                subject_id,
                predicate,
                value_json,
                epistemic_status,
                valid_from,
                valid_until,
                learned_at,
                evidence_event_ids_json,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.id,
                claim.subject_id,
                claim.predicate,
                value_json,
                claim.epistemic_status,
                claim.valid_from.isoformat() if claim.valid_from is not None else None,
                claim.valid_until.isoformat() if claim.valid_until is not None else None,
                claim.learned_at.isoformat(),
                evidence_json,
                claim.status,
            ),
        )


def get_claim(database_path: Path, claim_id: str) -> Claim | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                subject_id,
                predicate,
                value_json,
                epistemic_status,
                valid_from,
                valid_until,
                learned_at,
                evidence_event_ids_json,
                status
            FROM claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

    return _claim_from_row(row) if row is not None else None


def list_active_claims(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
) -> tuple[Claim, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                subject_id,
                predicate,
                value_json,
                epistemic_status,
                valid_from,
                valid_until,
                learned_at,
                evidence_event_ids_json,
                status
            FROM claims
            WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE'
            ORDER BY learned_at, id
            """,
            (subject_id, predicate),
        ).fetchall()

    return tuple(_claim_from_row(row) for row in rows)


def transition_claim(database_path: Path, claim_id: str, new_status: str) -> Claim:
    if new_status not in TERMINAL_STATUSES:
        raise ValueError(f"status terminal inválido: {new_status}")

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE claims
            SET status = ?
            WHERE id = ? AND status = 'ACTIVE'
            """,
            (new_status, claim_id),
        )

        if cursor.rowcount != 1:
            raise ValueError(f"claim não está ACTIVE: {claim_id}")

    updated = get_claim(database_path, claim_id)
    if updated is None:
        raise RuntimeError(f"claim desapareceu após atualização: {claim_id}")
    return updated


def set_current_claim(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
    value: object,
    epistemic_status: str,
    evidence_event_ids: tuple[str, ...] = (),
    valid_from: datetime | None = None,
) -> Claim:
    active_claims = list_active_claims(
        database_path,
        subject_id=subject_id,
        predicate=predicate,
    )

    for claim in active_claims:
        if claim.value == value and claim.epistemic_status == epistemic_status:
            return claim

    # Current-state claims are replaced explicitly so historical beliefs remain inspectable.
    for claim in active_claims:
        transition_claim(database_path, claim.id, "SUPERSEDED")

    new_claim = Claim.create(
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        epistemic_status=epistemic_status,
        evidence_event_ids=evidence_event_ids,
        valid_from=valid_from,
    )
    insert_claim(database_path, new_claim)
    return new_claim
