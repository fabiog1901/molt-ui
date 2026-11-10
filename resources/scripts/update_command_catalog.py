"""Capture CLI facts from molt's help into resources/command_catalog.json."""

import argparse
from pathlib import Path

from molt_ui.config import Settings
from molt_ui.catalog_update import generate_catalog, parse_help, write_catalog
from molt_ui.molt_process import MoltProcess

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "resources/command_catalog.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default=Settings.from_environment().executable)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    catalog = generate_catalog(MoltProcess(args.executable))
    write_catalog(catalog, args.output)
    print(f"Wrote {len(catalog.commands)} commands to {args.output}")


if __name__ == "__main__":
    main()
