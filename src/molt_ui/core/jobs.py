"""Bounded live output and process lifecycle, shared by terminal and HTTP adapters."""

from collections import deque
from dataclasses import dataclass
import json
import os
import signal
import subprocess
from threading import Lock, Thread
from uuid import uuid4

from .cli import CliError
from .aggregation import LogAggregator


@dataclass(frozen=True, slots=True)
class OutputEvent:
    sequence: int
    stream: str
    text: str
    data: dict[str, object] | None


class Job:
    def __init__(self, process: subprocess.Popen | None, command: str) -> None:
        self.id = str(uuid4())
        self.command = command
        self.process = process
        self._lock = Lock()
        self._events: deque[OutputEvent] = deque(maxlen=2000)
        self._sequence = 0
        self._status = "running" if process is not None else "imported"
        self._stopped = False
        self._returncode: int | None = None
        self._aggregation = LogAggregator()
        self.record = None
        self._save_record = None
        self._history_error = None
        self._thread = Thread(target=self._collect, daemon=True) if process is not None else None
        if self._thread:
            self._thread.start()

    def _consume(self, pipe, stream: str) -> None:
        while text := pipe.readline(16384):
            text = text.rstrip("\r\n")
            try:
                data = json.loads(text)
            except (ValueError, RecursionError):
                data = None
            if not isinstance(data, dict):
                data = None
            with self._lock:
                self._sequence += 1
                event = OutputEvent(self._sequence, stream, text, data)
                self._events.append(event)
                self._aggregation.ingest(event)

    def _read(self, pipe, stream: str) -> None:
        try:
            self._consume(pipe, stream)
        finally:
            pipe.close()

    def _collect(self) -> None:
        readers = [Thread(target=self._read, args=(pipe, stream), daemon=True)
                   for pipe, stream in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr"))]
        for reader in readers:
            reader.start()
        returncode = self.process.wait()
        for reader in readers:
            reader.join()
        with self._lock:
            self._returncode = returncode
            self._status = "stopped" if self._stopped else ("succeeded" if returncode == 0 else "failed")
            self._persist_record()

    def _persist_record(self) -> None:
        if self._save_record:
            try:
                saved = self._save_record({"status": self._status, "returncode": self._returncode,
                                           "aggregation": self._aggregation.snapshot(self._status)})
                if saved is not None:
                    self.record = saved
                self._history_error = None
            except Exception as exc:
                self._history_error = f"Could not update run history: {exc}"

    def attach_record(self, record: dict, save) -> None:
        with self._lock:
            self.record = record
            self._save_record = save
            self._persist_record()

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            return {
                "id": self.id, "command": self.command, "status": self._status,
                "returncode": self._returncode, "cursor": self._sequence,
                "truncated": bool(self._events and after < self._events[0].sequence - 1),
                "events": [event for event in self._events if event.sequence > after],
                "aggregation": self._aggregation.snapshot(self._status),
                "record": self.record,
                "history_error": self._history_error,
            }

    def table_logs(self, name: str, limit: int = 50) -> dict:
        with self._lock:
            return self._aggregation.table_logs(name, limit)

    def _signal(self, signum: int) -> None:
        if self.process is None:
            return
        try:
            if os.name == "posix":
                os.killpg(self.process.pid, signum)
            elif signum == signal.SIGTERM:
                self.process.terminate()
            else:
                self.process.kill()
        except ProcessLookupError:
            pass

    def stop(self) -> None:
        with self._lock:
            if self._status != "running" or self._stopped:
                return
            self._stopped = True
        self._signal(signal.SIGTERM)
        Thread(target=self._kill_later, daemon=True).start()

    def _kill_later(self) -> None:
        self._thread.join(2)
        if self._thread.is_alive():
            self._signal(signal.SIGKILL)

    def close(self) -> None:
        self.stop()
        if self._thread:
            self._thread.join(5)


class JobManager:
    """One active operation per service; retain only the latest run."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._job: Job | None = None

    def start(self, executable: str, arguments: list[str], environment: dict[str, str], command: str) -> Job:
        with self._lock:
            if self._job and self._job.snapshot()["status"] == "running":
                raise CliError("A command is already running. Stop it before starting another.")
            try:
                process = subprocess.Popen(
                    [executable, *arguments], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", shell=False,
                    env={**os.environ, **environment}, start_new_session=os.name == "posix",
                )
            except OSError as exc:
                raise CliError(f"Could not start CLI: {exc}") from exc
            self._job = Job(process, command)
            return self._job

    def get(self, job_id: str) -> Job:
        with self._lock:
            if not self._job or self._job.id != job_id:
                raise KeyError(job_id)
            return self._job

    def import_log(self, source) -> Job:
        """Read a text stream without running molt or retaining the whole file."""
        with self._lock:
            if self._job and self._job.snapshot()["status"] == "running":
                raise CliError("Stop the active command before importing a log.")
            job = Job(None, "fetch")
            job._consume(source, "stdout")
            if job.snapshot()["cursor"] == 0:
                raise ValueError("The log file is empty.")
            self._job = job
            return job

    def latest(self) -> Job | None:
        with self._lock:
            return self._job

    def close(self) -> None:
        with self._lock:
            job = self._job
        if job:
            job.close()
