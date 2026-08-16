import json
import sqlite3
from pathlib import Path

from simon.cli import main
from simon.entities import SIMON_ENTITY_ID


def test_main_initializes_storage_and_records_current_world_state(
    tmp_path: Path,
    capsys: object,
) -> None:
    result = main(["--data-dir", str(tmp_path)])

    assert result == 0
    database_path = tmp_path / "simon.db"
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        entity = connection.execute(
            "SELECT kind, name FROM entities WHERE id = ?",
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event = connection.execute(
            """
            SELECT id, kind, source, related_entity_ids_json
            FROM events
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()
        claim = connection.execute(
            """
            SELECT predicate, value_json, epistemic_status, evidence_event_ids_json, status
            FROM claims
            WHERE subject_id = ? AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()

    assert entity == ("system", "SIMON")
    assert event is not None
    assert event[1:3] == ("system.started", "system")
    assert tuple(json.loads(str(event[3]))) == (SIMON_ENTITY_ID,)

    assert claim is not None
    assert claim[0] == "storage.schema_version"
    assert json.loads(str(claim[1])) == 5
    assert claim[2] == "DIRECT_OBSERVATION"
    assert tuple(json.loads(str(claim[3]))) == (str(event[0]),)
    assert claim[4] == "ACTIVE"


def test_repeated_startup_does_not_duplicate_same_current_claim(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    assert main(["--data-dir", str(tmp_path)]) == 0

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        claim_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM claims
            WHERE subject_id = ?
              AND predicate = 'storage.schema_version'
              AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'"
        ).fetchone()

    assert claim_count == (1,)
    assert event_count == (2,)
