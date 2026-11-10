"""Resolve and validate molt commands once for preview, execution, and storage."""

from collections.abc import Mapping
import os
import shlex

from .catalog import command_spec
from .models import CommandPlan
from .options import CONNECTION_ENV, normalize_options


def _resolve(
    command: str,
    options: dict[str, str | bool],
    *,
    help_only: bool,
    source_kind: str | None,
    environment: Mapping[str, str],
):
    definition = command_spec(command)
    if help_only:
        return [*definition.arguments, "--help"], {}, {}, []
    normalized, omitted = normalize_options(
        command, options, source_kind=source_kind, environment=environment
    )
    values = dict(normalized)
    known = {option.name: option for option in definition.options}
    if command == "fetch" and values.get("bucket-path") and values.get("local-path"):
        raise ValueError("Choose either a staging bucket or a local staging directory.")
    if command.startswith("convert-"):
        values.setdefault("out", "-")
        values.setdefault("url", "")
        if not values.get("schema"):
            raise ValueError("Provide a source schema file path.")
    if command in {"fetch", "verify"}:
        for name in ("source", "target"):
            if not values.get(name) and not environment.get(CONNECTION_ENV[name]):
                raise ValueError(
                    f"Provide a {name} connection string or set {CONNECTION_ENV[name]}."
                )
    arguments = list(definition.arguments)
    overrides = {}
    for name, value in values.items():
        option = known[name]
        if option.kind == "bool":
            text = str(value).lower()
        else:
            if "\x00" in value:
                raise ValueError(f"--{name} must be text without null characters.")
            if option.kind == "int":
                try:
                    int(value)
                except ValueError as exc:
                    raise ValueError(f"--{name} must be an integer.") from exc
            text = value
        if name in CONNECTION_ENV:
            overrides[CONNECTION_ENV[name]] = text
        else:
            arguments.append(f"--{name}={text}")
    return arguments, overrides, normalized, omitted


def build_command(
    command: str,
    options: dict[str, str | bool],
    *,
    help_only: bool = False,
    source_kind: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    arguments, overrides, _, _ = _resolve(
        command,
        options,
        help_only=help_only,
        source_kind=source_kind,
        environment=os.environ if environment is None else environment,
    )
    return arguments, overrides


def build_plan(
    executable: str,
    command: str,
    options: dict[str, str | bool],
    *,
    help_only: bool = False,
    source_kind: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> CommandPlan:
    environment = os.environ if environment is None else environment
    arguments, overrides, normalized, omitted = _resolve(
        command,
        options,
        help_only=help_only,
        source_kind=source_kind,
        environment=environment,
    )
    if command in {"fetch", "verify"} and not help_only:
        for name in CONNECTION_ENV.values():
            if name not in overrides and environment.get(name):
                overrides[name] = environment[name]
    argv = (executable, *arguments)
    assignments = [f"{name}={shlex.quote(value)}" for name, value in overrides.items()]
    return CommandPlan(
        command=command,
        argv=argv,
        environment=overrides,
        options=normalized,
        omitted=tuple(omitted),
        invocation=" ".join([*assignments, shlex.join(argv)]),
    )
