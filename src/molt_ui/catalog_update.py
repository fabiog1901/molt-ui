"""Refresh the command catalog from the configured molt binary."""

import json
import logging
import re

from .core.errors import MoltError
from .core.models import CommandCatalog, CommandSpec, OptionSpec
from .molt_process import MoltProcess
from .repo import Repo
from .repo.repo import RepoError

logger = logging.getLogger(__name__)


def parse_help(help_text: str) -> tuple[OptionSpec, ...]:
    options = []
    current = None
    for line in help_text.splitlines():
        match = re.match(r"^ {2,6}(?:-\w, )?--([\w-]+)\s+(.*)$", line)
        if match:
            name, tail = match.groups()
            if name == "help":
                current = None
                continue
            parts = re.split(r"\s{2,}", tail, maxsplit=1)
            kind = "string" if len(parts) == 2 else "bool"
            if kind == "string" and parts[0] == "int":
                kind = "int"
            # Cobra renders this boolean with a value placeholder.
            if name == "use-copy":
                kind = "bool"
            current = {"name": name, "kind": kind, "description": parts[-1]}
            options.append(current)
        elif current and line.startswith(" " * 20):
            current["description"] += " " + line.strip()
        else:
            current = None
    for option in options:
        environment = re.search(r"\b(MOLT_[A-Z_]+)\s+environment variable\b", option["description"])
        if environment:
            option["environment_variable"] = environment[1]
        defaults = [value for value in re.findall(r"\(default ([^)]+)\)", option["description"])
                    if value != "<unknown>"]
        value = defaults[0] if defaults else ""
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value.strip('"')
        if option["kind"] == "bool":
            value = value == "true"
        elif option["kind"] == "int" and not value:
            value = "0"
        option["default"] = value
    return tuple(OptionSpec.model_validate(option) for option in options)


def subcommands(help_text: str) -> tuple[str, ...]:
    """Read Cobra's command section, excluding its recursive help utility."""
    match = re.search(r"^Available Commands:\n(.*?)(?=^\S|\Z)", help_text, re.MULTILINE | re.DOTALL)
    if not match:
        return ()
    return tuple(
        name for name in re.findall(r"^  ([\w-]+)\s+", match[1], re.MULTILINE)
        if name != "help"
    )


def generate_catalog(process: MoltProcess) -> CommandCatalog:
    commands = []

    def visit(arguments: tuple[str, ...]) -> None:
        result = process.run([*arguments, "--help"])
        if result.returncode:
            raise MoltError(result.stderr or result.stdout or "Could not read molt command help.")
        children = subcommands(result.stdout)
        options = parse_help(result.stdout)
        # A command can both execute and offer subcommands (for example fetch).
        flag_usage = f"molt {' '.join(arguments)} [flags]"
        runnable = arguments and (not children or flag_usage in result.stdout)
        if runnable:
            if not options and "Usage:" not in result.stdout:
                raise ValueError(f"Cannot read command parameters for {' '.join(arguments)}.")
            commands.append(CommandSpec(id="-".join(arguments), arguments=arguments, options=options))
        for name in children:
            visit((*arguments, name))
        if not arguments and not children:
            raise ValueError("Cannot discover molt commands: the help structure is incompatible.")

    visit(())
    return CommandCatalog(schema_version=1, commands=tuple(commands))


def refresh_catalog(process: MoltProcess, repo: Repo) -> CommandCatalog:
    """Load SQLite's catalog, regenerating it when the binary version changes."""
    try:
        saved = repo.get_catalog()
    except RepoError as exc:
        logger.warning("Cannot read the saved command catalog: %s", exc)
        saved = None
    try:
        result = process.run(["--version"])
        if result.returncode:
            raise MoltError(result.stderr.strip() or result.stdout.strip() or "molt --version failed.")
        version = result.stdout.strip() or result.stderr.strip()
        if not version:
            raise MoltError("molt --version returned no version.")
        if saved is not None and saved.version == version:
            return saved.catalog
        logger.info("Generating command catalog for %s", version)
        catalog = generate_catalog(process)
        repo.save_catalog(version, catalog)
        return catalog
    except (MoltError, RepoError, OSError, ValueError) as exc:
        if saved is not None:
            logger.warning("Could not refresh the molt command catalog; using the saved catalog: %s", exc)
            return saved.catalog
        raise MoltError(
            "No usable command catalog is stored in SQLite. "
            f"Set MOLT_EXECUTABLE to an available molt binary and restart. Details: {exc}"
        ) from exc
