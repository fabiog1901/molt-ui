"""Validate UI options and build argv once for both adapters."""

import os

from .catalog import COMMANDS


CONNECTION_ENV = {"source": "MOLT_SOURCE", "target": "MOLT_TARGET", "source-cdb": "MOLT_SOURCE_CDB"}


def command_definition(command: str) -> dict:
    for definition in COMMANDS:
        if definition["id"] == command:
            return definition
    raise ValueError("Unknown molt command.")


def build_command(command: str, options: dict[str, str | bool], *, help_only: bool = False) -> tuple[list[str], dict[str, str]]:
    definition = command_definition(command)
    if help_only:
        return [*definition["arguments"], "--help"], {}
    known = {option["name"]: option for option in definition["options"]}
    if options.keys() - known.keys():
        raise ValueError("Unknown option for the selected command.")
    values = dict(options)
    if command.startswith("convert-"):
        # Keep conversion output visible; skip database evaluation unless a URL is supplied.
        values.setdefault("out", "-")
        values.setdefault("url", "")
        if not values.get("schema"):
            raise ValueError("Provide a source schema file path.")
    if command in {"fetch", "verify"}:
        for name in ("source", "target"):
            if not values.get(name) and not os.environ.get(CONNECTION_ENV[name]):
                raise ValueError(f"Provide a {name} connection string or set {CONNECTION_ENV[name]}.")
        values.setdefault("log-file", "stdout")
    arguments = list(definition["arguments"])
    environment = {}
    for name, value in values.items():
        option = known[name]
        if option["kind"] == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"--{name} must be true or false.")
            text = str(value).lower()
        else:
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError(f"--{name} must be text without null characters.")
            if option["kind"] == "int":
                try:
                    int(value)
                except ValueError as exc:
                    raise ValueError(f"--{name} must be an integer.") from exc
            text = value
        if name in CONNECTION_ENV:
            environment[CONNECTION_ENV[name]] = text
        else:
            arguments.append(f"--{name}={text}")
    return arguments, environment
