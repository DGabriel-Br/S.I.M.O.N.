from __future__ import annotations

import argparse
from contextlib import closing
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCHEMA = 11
EXPECTED_MIGRATIONS = tuple(range(1, EXPECTED_SCHEMA + 1))


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"comando falhou ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_simon(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "simon.exe"
    return venv_dir / "bin" / "simon"


def _project_version() -> str:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _migration_names() -> tuple[str, ...]:
    return tuple(f"simon/migrations/{version:04d}_" for version in EXPECTED_MIGRATIONS)


def _assert_wheel(wheel_path: Path, expected_version: str) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        names = tuple(archive.namelist())
        for prefix in _migration_names():
            if not any(name.startswith(prefix) and name.endswith(".sql") for name in names):
                raise RuntimeError(f"wheel não contém migration esperada: {prefix}*.sql")

        entry_points_name = next(
            (name for name in names if name.endswith(".dist-info/entry_points.txt")),
            None,
        )
        if entry_points_name is None:
            raise RuntimeError("wheel não contém entry_points.txt")
        entry_points = archive.read(entry_points_name).decode("utf-8")
        if "simon = simon.cli:main" not in entry_points:
            raise RuntimeError("wheel não expõe o entry point simon = simon.cli:main")

        metadata_name = next(
            (name for name in names if name.endswith(".dist-info/METADATA")),
            None,
        )
        if metadata_name is None:
            raise RuntimeError("wheel não contém METADATA")
        metadata = archive.read(metadata_name).decode("utf-8")
        if f"Version: {expected_version}" not in metadata:
            raise RuntimeError("versão do wheel diverge do pyproject.toml")
        accepted_requires_python = (
            "Requires-Python: <3.15,>=3.14",
            "Requires-Python: >=3.14,<3.15",
        )
        if not any(value in metadata for value in accepted_requires_python):
            raise RuntimeError("wheel não preservou requires-python >=3.14,<3.15")


def _assert_sdist(sdist_path: Path) -> None:
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        names = tuple(archive.getnames())
        for prefix in _migration_names():
            if not any(f"/{prefix}" in f"/{name}" and name.endswith(".sql") for name in names):
                raise RuntimeError(f"sdist não contém migration esperada: {prefix}*.sql")
        required_suffixes = (
            "/pyproject.toml",
            "/README.md",
            "/SIMON_SPEC.md",
            "/scripts/rc_smoke.py",
        )
        for suffix in required_suffixes:
            if not any(name.endswith(suffix) for name in names):
                artifact = suffix.removeprefix("/")
                raise RuntimeError(f"sdist não contém artefato esperado: {artifact}")


def _assert_blank_database(simon_executable: Path, data_dir: Path) -> None:
    result = _run([str(simon_executable), "--data-dir", str(data_dir)], cwd=PROJECT_ROOT)
    if f"SQLite: pronto (schema {EXPECTED_SCHEMA})" not in result.stdout:
        raise RuntimeError("startup limpo não informou o schema esperado")

    database_path = data_dir / "simon.db"
    if not database_path.exists():
        raise RuntimeError("startup limpo não criou simon.db")

    with closing(sqlite3.connect(database_path)) as connection:
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if schema != EXPECTED_SCHEMA:
            raise RuntimeError(f"banco limpo terminou no schema {schema}")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    expected_tables = {
        "actions",
        "claims",
        "entities",
        "events",
        "experiences",
        "goals",
        "memories",
        "plans",
        "verification_results",
        "world_state",
    }
    missing = expected_tables - tables
    if missing:
        raise RuntimeError(f"banco limpo não criou tabelas esperadas: {sorted(missing)}")


def _extract_migrations_from_wheel(wheel_path: Path, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    with zipfile.ZipFile(wheel_path) as archive:
        migration_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("simon/migrations/") and name.endswith(".sql")
        )
        for name in migration_names:
            target = destination / Path(name).name
            target.write_bytes(archive.read(name))
            extracted.append(target)
    return extracted


def _assert_upgrade_from_seven(
    simon_executable: Path,
    wheel_path: Path,
    data_dir: Path,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = data_dir / "simon.db"
    migrations_dir = data_dir / "seed_migrations"
    migrations_dir.mkdir()
    migrations = _extract_migrations_from_wheel(wheel_path, migrations_dir)
    migrations_by_version = {int(path.name[:4]): path for path in migrations}

    with closing(sqlite3.connect(database_path)) as connection:
        for version in range(1, 8):
            migration_path = migrations_by_version.get(version)
            if migration_path is None:
                raise RuntimeError(
                    f"wheel não forneceu migration {version:04d} para teste de upgrade"
                )
            connection.executescript(migration_path.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO events (
                id, kind, occurred_at, source, payload_json, related_entity_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_rc_sentinel",
                "rc.sentinel",
                "2026-08-19T00:00:00+00:00",
                "system",
                "{}",
                "[]",
            ),
        )
        # closing() libera o handle no Windows, mas não confirma transações pendentes.
        connection.commit()

    _run([str(simon_executable), "--data-dir", str(data_dir)], cwd=PROJECT_ROOT)

    with closing(sqlite3.connect(database_path)) as connection:
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        sentinel = connection.execute(
            "SELECT id, kind FROM events WHERE id = ?",
            ("evt_rc_sentinel",),
        ).fetchone()
        world_revision = connection.execute(
            "SELECT revision FROM world_state WHERE singleton = 1"
        ).fetchone()

    if schema != EXPECTED_SCHEMA:
        raise RuntimeError(f"upgrade 7 -> {EXPECTED_SCHEMA} terminou no schema {schema}")
    if sentinel != ("evt_rc_sentinel", "rc.sentinel"):
        raise RuntimeError("upgrade perdeu o registro sentinela do schema 7")
    if world_revision is None:
        raise RuntimeError("upgrade não materializou world_state")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test reproduzível do release candidate v0.1"
    )
    parser.add_argument(
        "--keep-dist",
        action="store_true",
        help="mantém os artefatos existentes em dist antes do build",
    )
    args = parser.parse_args()

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv não encontrado no PATH")

    expected_version = _project_version()
    dist_dir = PROJECT_ROOT / "dist"
    if not args.keep_dist:
        shutil.rmtree(dist_dir, ignore_errors=True)
    _run([uv, "build"], cwd=PROJECT_ROOT)

    wheels = sorted(dist_dir.glob(f"simon_local-{expected_version}-*.whl"))
    sdists = sorted(dist_dir.glob(f"simon_local-{expected_version}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            "build deveria produzir 1 wheel e 1 sdist; "
            f"encontrados {len(wheels)} wheel(s) e {len(sdists)} sdist(s)"
        )

    wheel_path = wheels[0]
    sdist_path = sdists[0]
    _assert_wheel(wheel_path, expected_version)
    _assert_sdist(sdist_path)

    with tempfile.TemporaryDirectory(prefix="simon-rc-") as temporary:
        temporary_root = Path(temporary)
        venv_dir = temporary_root / "venv"
        _run([uv, "venv", "--python", sys.executable, str(venv_dir)], cwd=PROJECT_ROOT)
        venv_python = _venv_python(venv_dir)
        _run(
            [uv, "pip", "install", "--python", str(venv_python), str(wheel_path)],
            cwd=PROJECT_ROOT,
        )
        simon_executable = _venv_simon(venv_dir)

        version_result = _run([str(simon_executable), "--version"], cwd=temporary_root)
        if version_result.stdout.strip() != f"S.I.M.O.N. {expected_version}":
            raise RuntimeError("entry point instalado reportou versão inesperada")

        module_version = _run(
            [str(venv_python), "-m", "simon", "--version"],
            cwd=temporary_root,
        )
        if module_version.stdout.strip() != f"S.I.M.O.N. {expected_version}":
            raise RuntimeError("python -m simon reportou versão inesperada")

        help_result = _run([str(simon_executable), "--help"], cwd=temporary_root)
        required_commands = (
            "resume",
            "goal-propose",
            "plan-propose",
            "plan-run",
            "process-retry",
            "plan-patch",
            "file-retry",
            "plan-analyze",
            "analysis-retry",
            "goal-complete",
            "experience-remember",
        )
        for command in required_commands:
            if command not in help_result.stdout:
                raise RuntimeError(f"--help não expõe comando esperado: {command}")

        _assert_blank_database(simon_executable, temporary_root / "blank-data")
        _assert_upgrade_from_seven(
            simon_executable,
            wheel_path,
            temporary_root / "upgrade-data",
        )

    print("RC smoke: OK")
    print(f"Versão: {expected_version}")
    print(f"Wheel: {wheel_path.name}")
    print(f"Sdist: {sdist_path.name}")
    print(f"Schema limpo/upgrade: {EXPECTED_SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
