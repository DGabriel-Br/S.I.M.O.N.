import json
from pathlib import Path
import sqlite3

from simon.cli import main
from simon.entities import SIMON_ENTITY_ID


def test_main_initializes_storage_and_records_startup(tmp_path: Path, capsys: object) -> None:
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
            SELECT kind, source, related_entity_ids_json
            FROM events
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert entity == ("system", "SIMON")
    assert event is not None
    assert event[:2] == ("system.started", "system")
    assert tuple(json.loads(str(event[2]))) == (SIMON_ENTITY_ID,)
