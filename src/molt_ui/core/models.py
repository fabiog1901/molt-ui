"""Shared application data types, independent of either frontend."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


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
