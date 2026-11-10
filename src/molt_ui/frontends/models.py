"""Validated request and command-field models shared by the frontends.

These describe frontend inputs and display metadata. Process output and shared
application state belong in core.models, so the core never imports a frontend.
"""

from collections.abc import Mapping
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandSpec, OptionSpec


COMMAND_LABELS = {
    "fetch": "Fetch data",
    "verify": "Verify data",
    "convert-postgres": "Convert PostgreSQL schema",
    "convert-mysql": "Convert MySQL schema",
    "convert-oracle": "Convert Oracle schema",
}
COMMON = {
    "source", "target", "schema", "url", "out", "direct-copy", "bucket-path",
    "table-filter", "schema-filter", "table-handling", "mode", "non-interactive",
}
LABELS = {
    "source": "Source connection",
    "target": "Target connection",
    "source-cdb": "Oracle CDB connection",
    "direct-copy": "Direct copy (no staging)",
    "mode": "Fetch mode",
    "table-handling": "Target table handling",
    "schema": "Schema file",
    "out": "Output file",
    "url": "Evaluation database URL",
    "non-interactive": "Automatic prompt handling",
    "bucket-path": "Staging bucket",
    "local-path": "Local staging directory",
}
DISPLAY_CHOICES = {
    "logging": [(value, value) for value in (
        "trace", "debug", "info", "warn", "error", "fatal", "panic",
    )],
    "mode": [("data-load", "Load data"), ("export-only", "Export only"), ("import-only", "Import only")],
    "table-handling": [
        ("none", "Keep existing tables"),
        ("truncate-if-exists", "Truncate existing tables"),
        ("drop-on-target-and-recreate", "Drop and recreate tables"),
    ],
    "compression": [("none", "None"), ("gzip", "Gzip")],
    "format": [("original", "Original"), ("target", "Target"), ("crdb", "CockroachDB")],
}

# These describe the controls in our modal, not Molt's accepted CLI values.
MODAL_FIELDS = {
    "fetch": {"mode", "direct-copy", "source", "target"},
    "verify": {"source", "target"},
    "convert-postgres": {"schema"},
    "convert-mysql": {"schema"},
    "convert-oracle": {"schema"},
}
STAGING = {
    "bucket-path", "local-path", "local-path-crdb-access-addr", "local-path-listen-addr",
    "compression", "cleanup", "flush-rows", "flush-size", "assume-role", "import-assume-role",
    "import-batch-size", "import-region", "use-implicit-auth", "use-copy",
}


def source_dialect(source: str) -> str:
    return {
        "postgres": "postgres", "postgresql": "postgres", "mysql": "mysql",
        "oracle": "oracle", "cockroach": "cockroachdb", "cockroachdb": "cockroachdb",
    }.get(source.partition(":")[0].lower(), "unknown")


class FrontendModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicabilityRule(FrontendModel):
    test: Literal["data-load", "staged", "bucket", "local", "recreate", "empty-target", "dialect"]
    value: str | None = None


def option_rules(command: str, name: str) -> list[ApplicabilityRule]:
    tests = []
    if command == "fetch":
        if name == "direct-copy":
            tests.append("data-load")
        if name in STAGING:
            tests.append("staged")
        if name in {"assume-role", "import-assume-role", "import-region", "use-implicit-auth"}:
            tests.append("bucket")
        if name in {"local-path-crdb-access-addr", "local-path-listen-addr"}:
            tests.append("local")
        if name in {"dropped-constraints-file", "dropped-indexes-file"}:
            tests.append("recreate")
        if name == "require-empty-target":
            tests.append("empty-target")
    rules = [ApplicabilityRule(test=test) for test in tests]
    if command in {"fetch", "verify"}:
        if name.startswith("oracle-") or name in {"source-cdb", "source-oracle-wallet-location"}:
            rules.append(ApplicabilityRule(test="dialect", value="oracle"))
        if name.startswith("pglogical-") or name in {"flatten-partitioned-tables", "use-stats-based-sharding"}:
            rules.append(ApplicabilityRule(test="dialect", value="postgres"))
    return rules


class StartCommand(FrontendModel):
    command: str
    options: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    help_only: bool = False
    # Accepted for existing clients; source selection only controls frontend fields.
    source_kind: str | None = None


class OptionChoice(FrontendModel):
    value: str
    label: str


class CommandOption(FrontendModel):
    name: str
    kind: Literal["string", "int", "bool"]
    description: str
    advanced: bool
    secret: bool
    default: StrictStr | StrictBool
    required: bool
    environment_variable: str | None = None
    from_environment: bool = False
    default_label: str = ""
    default_by_source: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    stage: Literal[
        "operation", "connections", "common", "advanced", "logging", "metrics"
    ]
    rules: list[ApplicabilityRule] = Field(default_factory=list)
    label: str
    choices: list[OptionChoice] = Field(default_factory=list)
    brief: str

    @classmethod
    def from_spec(
        cls, option: OptionSpec, command: str, *, environment: Mapping[str, str]
    ) -> "CommandOption":
        name = option.name
        expected_kind = "bool" if name in {"direct-copy", "use-stats-based-sharding"} else "string"
        custom_controls = set(DISPLAY_CHOICES) | {
            "source", "target", "source-cdb", "schema", "out", "url", "direct-copy",
            "bucket-path", "local-path", "table-handling", "fetch-id", "continuation-token",
            "use-stats-based-sharding",
        }
        if command in COMMAND_LABELS and name in custom_controls and option.kind != expected_kind:
            raise MoltError(
                f"Cannot display {command}: --{name} changed to {option.kind}; "
                f"the configured control requires {expected_kind}."
            )
        choices = DISPLAY_CHOICES.get(name, []) if command in COMMAND_LABELS else []
        # A new CLI default must never appear as an empty or misleading dropdown.
        extra_defaults = {"disabled"} if name == "logging" else set()
        if choices and option.default not in {value for value, _ in choices} | extra_defaults:
            raise MoltError(
                f"Cannot display {command}: --{name} has a new default {option.default!r}. "
                "Update its dropdown configuration to match the command catalog."
            )
        env_name = option.environment_variable
        from_environment = bool(env_name and environment.get(env_name))
        stage = "advanced" if name not in COMMON else "common"
        if name in {
            "source", "target", "source-cdb", "source-oracle-wallet-location", "schema", "out", "url",
        }:
            stage = "connections"
        elif command == "fetch" and name in {"mode", "direct-copy"}:
            stage = "operation"
        elif name in {"bucket-path", "local-path"}:
            stage = "common"
        elif name in {"logging", "log-file", "use-console-writer"}:
            stage = "logging"
        elif name.startswith("metrics-") or name in {"opt-out-telemetry", "pprof-listen-addr"}:
            stage = "metrics"
        default, default_label = option.default, ""
        if name == "log-file" and command in {"fetch", "verify"}:
            default_label = command + "-{datetime}.log (generated automatically)"
        elif command == "verify" and name == "concurrency":
            default, default_label = "", "Automatic (CPU count)"
        return cls(
            name=name,
            kind=option.kind,
            description=option.description,
            default=default,
            advanced=name not in COMMON,
            secret=name in {"source", "target", "source-cdb", "url", "password"},
            required=(name == "schema" or (
                command in {"fetch", "verify"} and name in {"source", "target"} and not from_environment
            )),
            environment_variable=env_name,
            from_environment=from_environment,
            default_label=default_label,
            default_by_source={"postgres": True} if name == "use-stats-based-sharding" else {},
            stage=stage,
            rules=option_rules(command, name),
            label=LABELS.get(name, name.replace("-", " ").capitalize()),
            choices=[
                OptionChoice(value=value, label=label)
                for value, label in choices
            ],
            brief=option.description.split(". ", 1)[0].strip()[:180],
        )


class CommandDefinition(FrontendModel):
    id: str
    label: str
    arguments: list[str]
    options: list[CommandOption]
    default_source_dialect: str = "unknown"

    @classmethod
    def from_spec(
        cls, specification: CommandSpec, *, environment: Mapping[str, str] | None = None
    ) -> "CommandDefinition":
        environment = os.environ if environment is None else environment
        missing = MODAL_FIELDS.get(specification.id, set()) - {option.name for option in specification.options}
        if missing:
            raise MoltError(
                f"Cannot display {specification.id}: the command catalog no longer contains "
                + ", ".join(f"--{name}" for name in sorted(missing))
                + ". Update the modal configuration for this molt version."
            )
        options = [
            CommandOption.from_spec(option, specification.id, environment=environment)
            for option in specification.options
        ]
        priority = {"source": 0, "target": 1, "schema": 2, "url": 3, "out": 4}
        options.sort(key=lambda option: (option.advanced, priority.get(option.name, 10)))
        return cls(
            id=specification.id,
            label=COMMAND_LABELS.get(specification.id, specification.id),
            arguments=list(specification.arguments),
            options=options,
            default_source_dialect=source_dialect(environment.get("MOLT_SOURCE", "")),
        )
