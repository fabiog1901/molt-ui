"""Single-pass molt log aggregation, independent of retained console history."""

from collections import deque
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .jobs import OutputEvent


@dataclass(slots=True)
class TableProgress:
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
        elif run_status in {"failed", "stopped"} and self.phase not in {"exported", "imported", "verified"}:
            status = "interrupted"
        return {
            "name": self.name, "target": self.target, "exported": self.exported,
            "imported": self.imported, "errors": self.errors, "warnings": self.warnings,
            "log_lines": self.log_lines, "status": status, "phase": self.phase,
        }


def row_count(value: object) -> int | None:
    # Counts must be nonnegative integral JSON values, never booleans or floats.
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def message_table(message: str) -> str | None:
    """Only recognize messages that explicitly name a table; never use worker order."""
    for prefix in ("starting fetch for table ", "sharding not supported for table "):
        if message.startswith(prefix):
            return message[len(prefix):].split(" - ", 1)[0].strip() or None
    match = re.fullmatch(r"(?:finished )?truncating table \{([^{} ]+) ([^{}]+)\}", message)
    if match:
        return f"{match[1]}.{match[2]}"
    # COPY logs identify a table even though adjacent shard/batch records do not.
    identifier = r'(?:"(?:[^"]|"")+"|[\w$]+)'
    match = re.match(rf"running copy from query: COPY ({identifier}(?:\.{identifier})+)\s", message)
    return match[1] if match else None


class LogAggregator:
    def __init__(self) -> None:
        self.tables: dict[str, TableProgress] = {}
        self._aliases: dict[str, str] = {}
        # One global detail buffer, not an unbounded log list per table.
        self._details: deque[tuple[str, OutputEvent]] = deque(maxlen=2000)
        self._lines = 0
        self._errors = 0
        self._warnings = 0
        self._unassigned = 0
        self._unassigned_errors = 0
        self._unassigned_warnings = 0
        self._exported = 0
        self._imported = 0
        self._skipped = 0

    def ingest(self, event: OutputEvent) -> None:
        self._lines += 1
        data = event.data or {}
        level = str(data.get("level", "")).lower()
        error = int(level in {"error", "fatal", "panic"})
        warning = int(level in {"warn", "warning"})
        self._errors += error
        self._warnings += warning
        message = data.get("message", "")
        message = message if isinstance(message, str) else ""
        source, target = data.get("source_table"), data.get("target_table")
        if isinstance(source, str) and source:
            name = source
            if isinstance(target, str) and target:
                self._aliases[target] = name
        else:
            name = next((data[key] for key in ("table", "table_name", "target_table")
                         if isinstance(data.get(key), str) and data[key]), None)
            name = name or message_table(message)
            name = self._aliases.get(name, name)
        if not name:
            self._unassigned += 1
            self._unassigned_errors += error
            self._unassigned_warnings += warning
            return
        table = self.tables.get(name)
        if table is None:
            table = self.tables[name] = TableProgress(name)
        if isinstance(target, str) and target:
            table.target = target
        table.log_lines += 1
        table.errors += error
        table.warnings += warning
        self._details.append((name, event))
        lower = message.lower()
        if re.match(r"(?:ignoring|skipping) table\b|table skipped\b", lower) and not table.skipped:
            table.skipped = True
            self._skipped += 1
        if lower.startswith("starting fetch for table "):
            table.phase = "starting"
        elif lower == "data extraction phase starting":
            table.phase = "exporting"
        elif lower == "data extraction from source complete":
            table.phase = "exported"
            self._update_rows(table, "exported", data.get("num_rows"))
        elif lower == "starting data import on target":
            table.phase = "importing"
        elif lower == "data import on target for table complete":
            table.phase = "imported"
            self._update_rows(table, "imported", data.get("num_rows"))
        # Explicit cumulative counters, when supplied by other molt log variants.
        for field, keys in (("exported", ("rows_exported", "exported_rows")),
                            ("imported", ("rows_imported", "imported_rows"))):
            for key in keys:
                if key in data:
                    self._update_rows(table, field, data[key])

    def _update_rows(self, table: TableProgress, field: str, value: object) -> None:
        count = row_count(value)
        if count is None:
            return
        old = getattr(table, field)
        count = max(old or 0, count)
        setattr(table, field, count)
        if field == "exported":
            self._exported += count - (old or 0)
        else:
            self._imported += count - (old or 0)

    def snapshot(self, run_status: str = "running") -> dict:
        return {
            "totals": {
                "tables": len(self.tables), "errors": self._errors, "warnings": self._warnings,
                "skipped": self._skipped, "exported": self._exported, "imported": self._imported,
                "log_lines": self._lines, "unassigned": self._unassigned,
                "unassigned_errors": self._unassigned_errors, "unassigned_warnings": self._unassigned_warnings,
            },
            "tables": [table.snapshot(run_status) for table in self.tables.values()],
        }

    def table_logs(self, name: str, limit: int = 50) -> dict:
        name = self._aliases.get(name, name)
        table = self.tables[name]
        events = [event for table_name, event in self._details if table_name == name][-limit:]
        return {"name": name, "total": table.log_lines, "truncated": table.log_lines > len(events), "events": events}
