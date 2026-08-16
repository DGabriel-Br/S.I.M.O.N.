import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def _apply_migrations(connection: sqlite3.Connection) -> int:
    current_version = _schema_version(connection)

    for migration_path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        migration_version = int(migration_path.name[:4])
        if migration_version <= current_version:
            continue

        connection.executescript(migration_path.read_text(encoding="utf-8"))
        current_version = _schema_version(connection)

        if current_version != migration_version:
            raise RuntimeError(
                f"migration {migration_path.name} terminou no schema {current_version}"
            )

    return current_version


def initialize_storage(data_dir: Path) -> tuple[Path, int]:
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = data_dir / "simon.db"

    with sqlite3.connect(database_path) as connection:
        schema_version = _apply_migrations(connection)

    return database_path, schema_version
