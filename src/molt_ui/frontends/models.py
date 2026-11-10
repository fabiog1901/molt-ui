"""Validated request and command-field models shared by the frontends.

These describe frontend inputs and display metadata. Process output and shared
application state belong in core.models, so the core never imports a frontend.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from molt_ui.core.models import ApplicabilityRule, CommandSpec, OptionSpec


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

class FrontendModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartCommand(FrontendModel):
    command: str
    options: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    help_only: bool = False
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
    def from_spec(cls, option: OptionSpec, command: str) -> "CommandOption":
        name = option.name
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
        if name == "log-file":
            default_label = command + "-{datetime}.log (generated automatically)"
        elif command.startswith("convert-") and name == "url":
            default_label = "Disabled (no evaluation)"
        elif command == "verify" and name == "concurrency":
            default, default_label = "", "Automatic (CPU count)"
        return cls(
            name=name,
            kind=option.kind,
            description=option.description,
            default=default,
            advanced=name not in COMMON,
            secret=name in {"source", "target", "source-cdb", "url"},
            required=option.required,
            environment_variable=option.environment_variable,
            from_environment=option.from_environment,
            default_label=default_label,
            default_by_source=option.default_by_source,
            stage=stage,
            rules=list(option.rules),
            label=LABELS.get(name, name.replace("-", " ").capitalize()),
            choices=[
                OptionChoice(value=value, label=label)
                for value, label in DISPLAY_CHOICES.get(name, [])
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
    def from_spec(cls, specification: CommandSpec) -> "CommandDefinition":
        options = [CommandOption.from_spec(option, specification.id) for option in specification.options]
        priority = {"source": 0, "target": 1, "schema": 2, "url": 3, "out": 4}
        options.sort(key=lambda option: (option.advanced, priority.get(option.name, 10)))
        return cls(
            id=specification.id,
            label=COMMAND_LABELS.get(specification.id, specification.id),
            arguments=list(specification.arguments),
            options=options,
            default_source_dialect=specification.default_source_dialect,
        )
