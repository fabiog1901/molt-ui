"""Load the generated CLI specification; no UI or option policies live here."""

from functools import lru_cache
from importlib.metadata import distribution
from pathlib import Path

from .models import CommandCatalog, CommandSpec

RESOURCE = "resources/command_catalog.json"


def catalog_path() -> Path:
    checkout = Path(__file__).resolve().parents[3] / RESOURCE
    if checkout.is_file():
        return checkout
    # Poetry includes the JSON as distribution data, without making the generic
    # repository resources directory a top-level Python package.
    return Path(distribution("molt-ui").locate_file(RESOURCE)).resolve()


@lru_cache(maxsize=1)
def load_catalog() -> CommandCatalog:
    return CommandCatalog.model_validate_json(catalog_path().read_text(encoding="utf-8"))


def command_spec(command: str) -> CommandSpec:
    for specification in load_catalog().commands:
        if specification.id == command:
            return specification
    raise ValueError("Unknown molt command.")
