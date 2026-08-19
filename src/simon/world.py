from __future__ import annotations

import sqlite3
from pathlib import Path


def get_world_revision_in_connection(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT revision FROM world_state WHERE singleton = 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("estado de revisão do World não foi inicializado")

    revision: object = row[0]
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise TypeError("world revision inválida no banco")
    if revision < 0:
        raise ValueError("world revision não pode ser negativa")
    return revision


def get_world_revision(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return get_world_revision_in_connection(connection)


def advance_world_revision_in_connection(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        "UPDATE world_state SET revision = revision + 1 WHERE singleton = 1"
    )
    if cursor.rowcount != 1:
        raise RuntimeError("não foi possível avançar a revisão do World")
    return get_world_revision_in_connection(connection)
