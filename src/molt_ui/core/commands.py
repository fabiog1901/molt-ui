"""Build execution plans from catalog entries and explicitly selected values."""

from collections.abc import Mapping
import os
import shlex

from .catalog import command_spec
from .models import CommandCatalog, CommandPlan, RunRecord


def _invocation(argv: tuple[str, ...], environment: Mapping[str, str]) -> str:
    assignments = [f"{name}={shlex.quote(value)}" for name, value in environment.items()]
    return " ".join([*assignments, shlex.join(argv)])


def replay_plan(executable: str, record: RunRecord) -> CommandPlan:
    """Reuse recorded argv and connection overrides with the configured binary."""
    if record.origin not in {"command", "help"} or len(record.argv) < 2:
        raise ValueError("This history record has no saved command to re-run.")
    argv = (executable, *record.argv[1:])
    if any("\x00" in argument for argument in argv):
        raise ValueError("The saved command contains a null character and cannot be re-run.")
    return CommandPlan(
        command=record.command,
        argv=argv,
        environment=dict(record.environment),
        options=dict(record.options),
        invocation=_invocation(argv, record.environment),
    )


def build_plan(
    executable: str,
    command: str,
    options: dict[str, str | bool],
    *,
    catalog: CommandCatalog,
    help_only: bool = False,
    environment: Mapping[str, str] | None = None,
) -> CommandPlan:
    definition = command_spec(catalog, command)
    environment = os.environ if environment is None else environment
    arguments = list(definition.arguments)
    overrides = {}
    values = {} if help_only else dict(options)
    if help_only:
        arguments.append("--help")
    else:
        known = {option.name: option for option in definition.options}
        unknown = values.keys() - known.keys()
        if unknown:
            raise ValueError(
                "Options missing from the command catalog: "
                + ", ".join(f"--{name}" for name in sorted(unknown))
                + ". Reload the command form after updating molt."
            )
        for name, value in values.items():
            # This checks our argv contract. Molt validates types, accepted
            # values, required flags, and combinations of options.
            if not isinstance(value, (str, bool)):
                raise ValueError(f"--{name} must be text or a boolean.")
            text = str(value).lower() if isinstance(value, bool) else value
            if "\x00" in text:
                raise ValueError(f"--{name} contains a null character and cannot be passed to molt.")
            env_name = known[name].environment_variable
            if env_name:
                overrides[env_name] = text
            else:
                arguments.append(f"--{name}={text}")
        for option in definition.options:
            env_name = option.environment_variable
            if env_name and env_name not in overrides and environment.get(env_name):
                overrides[env_name] = environment[env_name]
    argv = (executable, *arguments)
    return CommandPlan(
        command=command,
        argv=argv,
        environment=overrides,
        options=values,
        invocation=_invocation(argv, overrides),
    )


def build_command(
    command: str,
    options: dict[str, str | bool],
    *,
    catalog: CommandCatalog,
    help_only: bool = False,
    environment: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    plan = build_plan("molt", command, options, catalog=catalog, help_only=help_only, environment=environment)
    return list(plan.argv[1:]), plan.environment
