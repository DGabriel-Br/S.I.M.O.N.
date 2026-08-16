import sqlite3
from pathlib import Path

from simon.storage import MIGRATIONS_DIR, initialize_storage


def test_initialize_storage_applies_migrations(tmp_path: Path) -> None:
    database_path, schema_version = initialize_storage(tmp_path)

    assert database_path.exists()
    assert schema_version == 5

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('events', 'entities', 'claims', 'goals', 'plans')"
            ).fetchall()
        }

    assert tables == {"events", "entities", "claims", "goals", "plans"}


def test_initialize_storage_upgrades_schema_four_without_losing_data(tmp_path: Path) -> None:
    database_path = tmp_path / "simon.db"
    tmp_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        for version in range(1, 5):
            migration = next(MIGRATIONS_DIR.glob(f"{version:04d}_*.sql"))
            connection.executescript(migration.read_text(encoding="utf-8"))

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
        connection.execute(
            """
            INSERT INTO claims (
                id,
                subject_id,
                predicate,
                value_json,
                epistemic_status,
                learned_at,
                evidence_event_ids_json,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "clm_existing",
                "ent_existing",
                "status",
                '"working"',
                "DIRECT_OBSERVATION",
                "2026-08-16T12:00:00+00:00",
                '["evt_existing"]',
                "ACTIVE",
            ),
        )

        connection.execute(
            """
            INSERT INTO goals (
                id,
                title,
                origin,
                desired_state_json,
                success_criteria_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gol_existing",
                "Existing Goal",
                "USER",
                '{"status":"resolved"}',
                '[{"kind":"test_passes"}]',
                "ACTIVE",
                "2026-08-16T12:00:00+00:00",
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
        claim = connection.execute(
            "SELECT id, predicate FROM claims WHERE id = ?",
            ("clm_existing",),
        ).fetchone()
        goal = connection.execute(
            "SELECT id, title FROM goals WHERE id = ?",
            ("gol_existing",),
        ).fetchone()
        plans_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'plans'"
        ).fetchone()

    assert schema_version == 5
    assert event == ("evt_existing", "system.started")
    assert entity == ("ent_existing", "Existing Project")
    assert claim == ("clm_existing", "status")
    assert goal == ("gol_existing", "Existing Goal")
    assert plans_table == ("plans",)


def test_initialize_storage_is_idempotent(tmp_path: Path) -> None:
    first_database_path, first_schema_version = initialize_storage(tmp_path)
    second_database_path, second_schema_version = initialize_storage(tmp_path)

    assert second_database_path == first_database_path
    assert first_schema_version == 5
    assert second_schema_version == 5
