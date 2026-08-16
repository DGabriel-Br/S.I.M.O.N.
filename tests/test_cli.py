from pathlib import Path
import sqlite3

from simon.cli import main


def test_main_initializes_storage_and_records_startup(tmp_path: Path, capsys: object) -> None:
    result = main(["--data-dir", str(tmp_path)])

    assert result == 0
    database_path = tmp_path / "simon.db"
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        event = connection.execute(
            "SELECT kind, source FROM events ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()

    assert event == ("system.started", "system")
