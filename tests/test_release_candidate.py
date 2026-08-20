from __future__ import annotations

import tomllib
from pathlib import Path

from simon import __version__
from simon.cli import build_parser
from simon.storage import MIGRATIONS_DIR, initialize_storage

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_development_version_is_consistent_and_release_metadata_is_preserved() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")

    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (PROJECT_ROOT / "RELEASE_NOTES_0.1.0.md").read_text(encoding="utf-8")

    assert __version__ == "0.2.0.dev0"
    assert pyproject["project"]["version"] == __version__
    assert f'name = "simon-local"\nversion = "{__version__}"' in lock
    assert "## [0.1.0] - 2026-08-19" in changelog
    assert "# S.I.M.O.N. 0.1.0" in release_notes


def test_release_declares_python_314_and_packaged_entry_point() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.14,<3.15"
    assert pyproject["project"]["scripts"]["simon"] == "simon.cli:main"
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/simon"
    ]


def test_release_migrations_are_contiguous_through_schema_11(tmp_path: Path) -> None:
    migration_versions = tuple(
        int(path.name[:4])
        for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    )

    assert migration_versions == tuple(range(1, 12))
    _, schema_version = initialize_storage(tmp_path)
    assert schema_version == 11


def test_current_help_preserves_release_surface_and_exposes_executive() -> None:
    help_text = build_parser().format_help()

    for command in (
        "resume",
        "executive-next",
        "executive-step",
        "goal-propose",
        "goal-accept",
        "plan-propose",
        "plan-materialize",
        "plan-run",
        "process-retry",
        "plan-patch",
        "file-retry",
        "plan-analyze",
        "analysis-retry",
        "process-verify",
        "file-verify",
        "goal-assess",
        "goal-complete",
        "experience-remember",
    ):
        assert command in help_text
