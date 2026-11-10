"""Look up commands in an explicitly supplied, validated catalog."""

from .models import CommandCatalog, CommandSpec


def command_spec(catalog: CommandCatalog, command: str) -> CommandSpec:
    for specification in catalog.commands:
        if specification.id == command:
            return specification
    raise ValueError("Unknown molt command.")
