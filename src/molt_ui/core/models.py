"""Shared application data types, independent of either frontend."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class CatalogState(ImmutableModel):
    version: str
    sha256: str


class ApplicabilityRule(ImmutableModel):
    test: Literal["data-load", "staged", "bucket", "local", "recreate", "empty-target", "dialect"]
    value: str | None = None


class OptionSpec(ImmutableModel):
    name: str
    kind: Literal["string", "int", "bool"]
    description: str
    default: StrictStr | StrictBool
    allowed_values: tuple[str, ...] = ()
    environment_variable: str | None = None
    required: bool = False
    from_environment: bool = False
    default_by_source: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    rules: tuple[ApplicabilityRule, ...] = ()


class CommandSpec(ImmutableModel):
    id: str
    arguments: tuple[str, ...] = Field(min_length=1)
    options: tuple[OptionSpec, ...]
    default_source_dialect: str = "unknown"

    @model_validator(mode="after")
    def unique_options(self):
        names = [option.name for option in self.options]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate options in command {self.id}.")
        return self


class CommandCatalog(ImmutableModel):
    schema_version: Literal[1]
    commands: tuple[CommandSpec, ...]

    @model_validator(mode="after")
    def unique_commands(self):
        names = [command.id for command in self.commands]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate commands in catalog.")
        return self


class LogEntry(ImmutableModel):
    stream: Literal["stdout", "stderr"]
    data: dict[str, object]


class CommandResult(ImmutableModel):
    stdout: str
    stderr: str
    returncode: int
    logs: tuple[LogEntry, ...] = ()


class OutputEvent(ImmutableModel):
    sequence: int
    stream: Literal["stdout", "stderr"]
    text: str
    data: dict[str, object] | None


class CommandPlan(ImmutableModel):
    command: str
    argv: tuple[str, ...] = Field(min_length=1)
    environment: dict[str, str]
    options: dict[str, str | bool]
    omitted: tuple[str, ...] = ()
    invocation: str


class RunRecord(ImmutableModel):
    id: str
    command: str
    origin: str
    invocation: str | None = None
    argv: list[str]
    environment: dict[str, str]
    options: dict[str, str | bool]
    started_at: str
    finished_at: str | None = None
    status: str
    returncode: int | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None


class RunSnapshot(ImmutableModel):
    id: str
    command: str
    status: str
    returncode: int | None = None
    cursor: int
    truncated: bool
    events: tuple[OutputEvent, ...]
    aggregation: dict[str, Any]
    record: RunRecord | None = None
    history_error: str | None = None


class TableLogs(ImmutableModel):
    name: str
    total: int
    truncated: bool
    events: tuple[OutputEvent, ...]


class TableProgress(BaseModel):
    """Mutable aggregation state; updates are owned by the log aggregator."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    target: str | None = None
    exported: int | None = None
    imported: int | None = None
    errors: int = 0
    warnings: int = 0
    log_lines: int = 0
    skipped: bool = False
    phase: str = "discovered"

    def snapshot(self, run_status: str) -> dict:
        status = self.phase
        if self.errors:
            status = "error"
        elif self.skipped:
            status = "skipped"
        elif self.warnings:
            status = "warning"
        elif run_status in {"failed", "stopped"} and self.phase not in {
            "exported",
            "imported",
            "verified",
        }:
            status = "interrupted"
        return {
            "name": self.name,
            "target": self.target,
            "exported": self.exported,
            "imported": self.imported,
            "errors": self.errors,
            "warnings": self.warnings,
            "log_lines": self.log_lines,
            "status": status,
            "phase": self.phase,
        }
