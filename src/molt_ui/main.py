"""Command-line entry point for the Molt UI server."""

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from molt_ui.config import Settings


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Start the Molt UI web app.",
        epilog="Additional --key=value options are passed to Uvicorn as string values.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Address to bind (default: %(default)s)"
    )
    parser.add_argument(
        "--port",
        type=port_number,
        default=8000,
        help="Port to bind (default: %(default)s)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Reload the server when source files change"
    )
    parser.add_argument(
        "--drop-db", action="store_true",
        help="Delete the configured database and start with a fresh schema",
    )
    args, extra_args = parser.parse_known_args(argv)
    options = vars(args)
    drop_db = options.pop("drop_db")
    remaining = iter(extra_args)
    for argument in remaining:
        key, separator, value = argument.partition("=")
        if not key.startswith("--") or not key[2:].replace("-", "_").isidentifier():
            parser.error(f"expected --key=value, got {argument!r}")
        if not separator:
            value = next(remaining, None)
            if value is None or value.startswith("--"):
                parser.error(f"{key} requires a value")
        options[key[2:].replace("-", "_")] = value
    if drop_db:
        database = Settings.from_environment().database
        if database != ":memory:":
            target = Path(database).expanduser().resolve()
            target.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(f"{target}{suffix}").unlink(missing_ok=True)
    uvicorn.run("molt_ui.api.app:app", **options)


if __name__ == "__main__":
    main()
