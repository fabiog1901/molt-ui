"""In-memory run state and log aggregation, independent of subprocess and SQLite."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING

from .aggregation import LogAggregator
from .errors import MoltError
from .logs import parse_line
from .models import CommandPlan, OutputEvent, RunRecord, RunSnapshot, TableLogs

if TYPE_CHECKING:
    from molt_ui.molt_process import MoltProcess, ProcessHandle


class Run:
    def __init__(
        self,
        command: str,
        *,
        imported: bool = False,
        record: RunRecord | None = None,
        on_complete: Callable[[RunSnapshot], RunRecord] | None = None,
        on_output: Callable[[OutputEvent], None] | None = None,
    ) -> None:
        self.id = record.id if record is not None else datetime.now(timezone.utc).strftime('%Y-%m-%dT%H.%M.%SZ')
        self.command = command
        self.handle: ProcessHandle | None = None
        self._lock = Lock()
        self._events: deque[OutputEvent] = deque(maxlen=2000)
        self._sequence = 0
        self._status = "imported" if imported else "running"
        self._returncode: int | None = None
        self._aggregation = LogAggregator()
        self._record = record
        self._on_output = on_output
        self._on_complete = on_complete
        self._history_error: str | None = None
        self._error: str | None = None
        self._diagnostic: str | None = None
        self._stderr: str | None = None

    def ingest(self, text: str, stream: str) -> None:
        data = parse_line(text)
        with self._lock:
            self._sequence += 1
            event = OutputEvent(
                sequence=self._sequence, stream=stream, text=text, data=data
            )
            self._events.append(event)
            self._aggregation.ingest(event)
            if data and str(data.get("level", "")).lower() in {"error", "fatal", "panic"}:
                message = data.get("message")
                if isinstance(message, str) and message.strip():
                    self._diagnostic = message.strip()
            if stream == "stderr" and text.strip():
                self._stderr = text.strip()
        on_output = self._on_output
        if on_output:
            try:
                on_output(event)
            except Exception as exc:
                with self._lock:
                    self._history_error = f"Could not capture command output: {exc}"
                    self._on_output = None

    def consume(self, source) -> None:
        while text := source.readline(16384):
            self.ingest(text.rstrip("\r\n"), "stdout")

    def _snapshot(
        self,
        after: int = 0,
        *,
        status: str | None = None,
        returncode: int | None = None,
    ) -> RunSnapshot:
        status = self._status if status is None else status
        return RunSnapshot(
            id=self.id,
            command=self.command,
            status=status,
            returncode=self._returncode if returncode is None else returncode,
            cursor=self._sequence,
            truncated=bool(self._events and after < self._events[0].sequence - 1),
            events=tuple(event for event in self._events if event.sequence > after),
            aggregation=self._aggregation.snapshot(status),
            record=self._record,
            history_error=self._history_error,
            error=self._error,
        )

    def snapshot(self, after: int = 0) -> RunSnapshot:
        with self._lock:
            return self._snapshot(after)

    def finish(self, returncode: int, stopped: bool) -> None:
        status = (
            "stopped" if stopped else ("succeeded" if returncode == 0 else "failed")
        )
        with self._lock:
            if status == "failed":
                reason = (
                    f"Molt was terminated by signal {-returncode}."
                    if returncode < 0 else f"Molt exited with code {returncode}."
                )
                diagnostic = self._diagnostic or self._stderr
                self._error = f"{reason} {diagnostic}" if diagnostic else reason
            final = self._snapshot(status=status, returncode=returncode)
        record, error = self._record, self._history_error
        if self._on_complete:
            try:
                # Storage callbacks run outside the log/state lock. Publish the
                # terminal state once the completion record has been attempted.
                record = self._on_complete(final)
            except Exception as exc:
                error = f"Could not update run history: {exc}"
        with self._lock:
            self._returncode = returncode
            self._status = status
            self._record = record
            self._history_error = error

    def attach_record(self, record: RunRecord | None) -> None:
        with self._lock:
            self._record = record

    def table_logs(self, name: str, limit: int = 50) -> TableLogs:
        with self._lock:
            details = self._aggregation.table_logs(name, limit)
            return TableLogs(
                name=details["name"],
                total=details["total"],
                truncated=details["truncated"],
                events=tuple(details["events"]),
            )

    def stop(self) -> None:
        if self.handle:
            self.handle.stop()

    def close(self) -> None:
        if self.handle:
            self.handle.close()


class RunManager:
    """Retain the latest run and enforce one active operation per service."""

    def __init__(self, process: MoltProcess) -> None:
        self._process = process
        self._lock = Lock()
        self._run: Run | None = None

    def _ensure_idle(self) -> None:
        if self._run and self._run.snapshot().status == "running":
            raise MoltError(
                "A command is already running. Stop it before starting another."
            )

    def ensure_idle(self) -> None:
        with self._lock:
            self._ensure_idle()

    def start(
        self,
        plan: CommandPlan,
        *,
        record: RunRecord | None = None,
        on_complete: Callable[[RunSnapshot], RunRecord] | None = None,
        on_output: Callable[[OutputEvent], None] | None = None,
        on_log_file: Callable[[str | None], None] | None = None,
    ) -> Run:
        with self._lock:
            self._ensure_idle()
            if plan.argv[0] != self._process.executable:
                raise MoltError(
                    "The execution plan does not match the configured molt executable."
                )
            run = Run(plan.command, record=record, on_complete=on_complete, on_output=on_output)
            run.handle = self._process.start(
                plan.argv[1:],
                environment=plan.environment,
                on_output=run.ingest,
                on_exit=run.finish,
                **({"on_log_file": on_log_file} if on_log_file is not None else {}),
            )
            self._run = run
            return run

    def import_log(
        self, source, *, save: Callable[[RunSnapshot], RunRecord] | None = None,
        on_output: Callable[[OutputEvent], None] | None = None,
    ) -> Run:
        with self._lock:
            self._ensure_idle()
            run = Run("fetch", imported=True, on_output=on_output)
            run.consume(source)
            if run.snapshot().cursor == 0:
                raise ValueError("The log file is empty.")
            if save:
                record = save(run.snapshot())
                run.attach_record(record)
                run.id = record.id
            self._run = run
            return run

    def get(self, run_id: str) -> Run:
        with self._lock:
            if self._run is None or self._run.id != run_id:
                raise KeyError(run_id)
            return self._run

    def latest(self) -> Run | None:
        with self._lock:
            return self._run

    def close(self) -> None:
        with self._lock:
            run = self._run
        if run:
            run.close()
