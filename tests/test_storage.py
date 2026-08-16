from pathlib import Path
import sqlite3

from simon.storage import initialize_storage


def test_initialize_storage_applies_event_migration(tmp_path: Path) -> None:
    database_path, schema_version = initialize_storage(tmp_path)

    assert database_path.exists()
    assert schema_version == 1

    with sqlite3.connect(database_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'events'"
        ).fetchone()

    assert table == ("events",)


def test_initialize_storage_is_idempotent(tmp_path: Path) -> None:
    first_database_path, first_schema_version = initialize_storage(tmp_path)
    second_database_path, second_schema_version = initialize_storage(tmp_path)

    assert second_database_path == first_database_path
    assert first_schema_version == 1
    assert second_schema_version == 1
