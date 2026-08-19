import sqlite3
from pathlib import Path

from simon.storage import MIGRATIONS_DIR, initialize_storage


def test_initialize_storage_applies_migrations(tmp_path: Path) -> None:
    database_path, schema_version = initialize_storage(tmp_path)

    assert database_path.exists()
    assert schema_version == 11

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name IN ("
                "'events', 'entities', 'claims', 'goals', "
                "'plans', 'actions', 'verification_results', 'experiences', 'memories', 'world_state'"
                ")"
            ).fetchall()
        }

    assert tables == {
        "events",
        "entities",
        "claims",
        "goals",
        "plans",
        "actions",
        "verification_results",
        "experiences",
        "memories",
        "world_state",
    }


def test_initialize_storage_upgrades_schema_seven_without_losing_data(tmp_path: Path) -> None:
    database_path = tmp_path / "simon.db"
    tmp_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        for version in range(1, 8):
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
        connection.execute(
            """
            INSERT INTO plans (
                id,
                goal_id,
                revision,
                steps_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pln_existing",
                "gol_existing",
                1,
                '[{"id":"step_1","description":"Existing Step"}]',
                "ACTIVE",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO actions (
                id,
                goal_id,
                plan_id,
                step_id,
                kind,
                input_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "act_existing",
                "gol_existing",
                "pln_existing",
                "step_1",
                "test.run",
                "{}",
                "COMPLETED",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:00:00+00:00",
            ),
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
                "ver_existing",
                "ACTION",
                "act_existing",
                '[{"kind":"test_passes"}]',
                "VERIFIED",
                '["evt_existing"]',
                '{"passed":true}',
                2,
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
        plan = connection.execute(
            "SELECT id, revision, based_on_world_revision FROM plans WHERE id = ?",
            ("pln_existing",),
        ).fetchone()
        world_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()
        action = connection.execute(
            "SELECT id, status FROM actions WHERE id = ?",
            ("act_existing",),
        ).fetchone()
        verification = connection.execute(
            "SELECT id, status FROM verification_results WHERE id = ?",
            ("ver_existing",),
        ).fetchone()
        experience_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'experiences'"
        ).fetchone()

    assert schema_version == 11
    assert event == ("evt_existing", "system.started")
    assert entity == ("ent_existing", "Existing Project")
    assert claim == ("clm_existing", "status")
    assert goal == ("gol_existing", "Existing Goal")
    assert plan == ("pln_existing", 1, 1)
    assert world_revision == (1,)
    assert action == ("act_existing", "COMPLETED")
    assert verification == ("ver_existing", "VERIFIED")
    assert experience_table == ("experiences",)
    with sqlite3.connect(upgraded_path) as connection:
        memory_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
        ).fetchone()
    assert memory_table == ("memories",)


def test_initialize_storage_is_idempotent(tmp_path: Path) -> None:
    first_database_path, first_schema_version = initialize_storage(tmp_path)
    second_database_path, second_schema_version = initialize_storage(tmp_path)

    assert second_database_path == first_database_path
    assert first_schema_version == 11
    assert second_schema_version == 11


def test_initialize_storage_upgrades_schema_eight_without_losing_experience(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "simon.db"
    tmp_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        for version in range(1, 9):
            migration = next(MIGRATIONS_DIR.glob(f"{version:04d}_*.sql"))
            connection.executescript(migration.read_text(encoding="utf-8"))

        connection.execute(
            """
            INSERT INTO experiences (
                id,
                title,
                status,
                outcome,
                event_ids_json,
                action_ids_json,
                verification_ids_json,
                summary,
                started_at,
                ended_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "exp_existing",
                "Existing Experience",
                "CLOSED",
                "SUCCESS",
                "[]",
                "[]",
                "[]",
                "Existing summary",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:05:00+00:00",
                "2026-08-16T12:05:00+00:00",
            ),
        )

    upgraded_path, schema_version = initialize_storage(tmp_path)

    with sqlite3.connect(upgraded_path) as connection:
        experience = connection.execute(
            "SELECT id, outcome, summary FROM experiences WHERE id = ?",
            ("exp_existing",),
        ).fetchone()
        memory_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
        ).fetchone()

    assert schema_version == 11
    assert experience == ("exp_existing", "SUCCESS", "Existing summary")
    assert memory_table == ("memories",)


def test_initialize_storage_upgrades_schema_nine_and_preserves_actions(tmp_path: Path) -> None:
    database_path = tmp_path / "simon.db"
    tmp_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        for version in range(1, 10):
            migration = next(MIGRATIONS_DIR.glob(f"{version:04d}_*.sql"))
            connection.executescript(migration.read_text(encoding="utf-8"))

        connection.execute(
            """
            INSERT INTO goals (
                id, title, origin, desired_state_json, success_criteria_json,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gol_schema9",
                "Existing Goal",
                "USER",
                '{"status":"active"}',
                '[{"kind":"done"}]',
                "ACTIVE",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO plans (
                id, goal_id, revision, steps_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pln_schema9",
                "gol_schema9",
                1,
                '[{"id":"step_1","description":"Existing Step"}]',
                "ACTIVE",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO actions (
                id, goal_id, plan_id, step_id, kind, input_json, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "act_schema9",
                "gol_schema9",
                "pln_schema9",
                "step_1",
                "test.run",
                "{}",
                "COMPLETED",
                "2026-08-16T12:00:00+00:00",
                "2026-08-16T12:00:00+00:00",
            ),
        )

    upgraded_path, schema_version = initialize_storage(tmp_path)

    with sqlite3.connect(upgraded_path) as connection:
        preserved = connection.execute(
            "SELECT id, status FROM actions WHERE id = 'act_schema9'"
        ).fetchone()
        migrated_plan = connection.execute(
            "SELECT based_on_world_revision FROM plans WHERE id = 'pln_schema9'"
        ).fetchone()
        connection.execute(
            """
            INSERT INTO actions (
                id, goal_id, plan_id, step_id, kind, input_json, status,
                created_at, started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "act_waiting",
                "gol_schema9",
                "pln_schema9",
                "step_1",
                "user.ask",
                '{"prompt":"Pergunta"}',
                "WAITING",
                "2026-08-16T12:10:00+00:00",
                "2026-08-16T12:10:00+00:00",
                "2026-08-16T12:10:00+00:00",
            ),
        )
        waiting = connection.execute(
            "SELECT status FROM actions WHERE id = 'act_waiting'"
        ).fetchone()

    assert schema_version == 11
    assert preserved == ("act_schema9", "COMPLETED")
    assert migrated_plan == (0,)
    assert waiting == ("WAITING",)
