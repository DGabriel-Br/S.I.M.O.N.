import argparse
from pathlib import Path
from collections.abc import Sequence

from simon import __version__
from simon.events import Event, append_event
from simon.storage import initialize_storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simon",
        description="S.I.M.O.N. - Simples Inteligência, Mais Ou Menos Normal",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".simon"),
        help="diretório local usado pelo SIMON para persistência",
    )
    parser.add_argument("--version", action="version", version=f"S.I.M.O.N. {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database_path, schema_version = initialize_storage(args.data_dir.resolve())

    append_event(
        database_path,
        Event.create(
            kind="system.started",
            source="system",
            payload={"version": __version__, "schema_version": schema_version},
        ),
    )

    print(f"S.I.M.O.N. {__version__}")
    print(f"Dados: {database_path.parent}")
    print(f"SQLite: pronto (schema {schema_version})")
    return 0
