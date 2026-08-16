from pathlib import Path
import sqlite3

from simon.storage import MIGRATIONS_DIR, initialize_storage


def test_initialize_storage_applies_migrations(tmp_path: Path) -> None:
    database_path, schema_version = initialize_storage(tmp_path)

    assert database_path.exists()
    assert schema_version == 3

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('events', 'entities', 'claims')"
            ).fetchall()
        }

    assert tables == {"events", "entities", "claims"}


def test_initialize_storage_upgrades_schema_two_without_losing_data(tmp_path: Path) -> None:
    database_path = tmp_path / "simon.db"
    tmp_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            (MIGRATIONS_DIR / "0001_events.sql").read_text(encoding="utf-8")
        )
        connection.executescript(
            (MIGRATIONS_DIR / "0002_entities.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            """
            INSERT INTO events (
                id,
                kind,
                occurred_at,
                source,
                payload_json,
                related_entity_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_existing",
                "system.started",
                "2026-08-16T12:00:00+00:00",
                "system",
                "{}",
                "[]",
            ),
        )
        connection.execute(
            """
            INSERT INTO entities (id, kind, name, aliases_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "ent_existing",
                "project",
                "Existing Project",
                "[]",
                "2026-08-16T12:00:00+00:00",
            ),
        )

    upgraded_path, schema_version = initialize_storage(tmp_path)

    with sqlite3.connect(upgraded_path) as connection:
        event = connection.execute(
            "SELECT id, kind FROM events WHERE id = ?",
            ("evt_existing",),
        ).fetchone()
        entity = connection.execute(
            "SELECT id, name FROM entities WHERE id = ?",
            ("ent_existing",),
        ).fetchone()
        claims_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'claims'"
        ).fetchone()

    assert schema_version == 3
    assert event == ("evt_existing", "system.started")
    assert entity == ("ent_existing", "Existing Project")
    assert claims_table == ("claims",)


def test_initialize_storage_is_idempotent(tmp_path: Path) -> None:
    first_database_path, first_schema_version = initialize_storage(tmp_path)
    second_database_path, second_schema_version = initialize_storage(tmp_path)

    assert second_database_path == first_database_path
    assert first_schema_version == 3
    assert second_schema_version == 3
