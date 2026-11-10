"""SQLite persistence for command records; no execution or frontend policy."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from uuid import uuid4

from molt_ui.core.models import RunRecord


class RepoError(RuntimeError):
    """Persistent metadata could not be read or written."""


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repo:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            target = Path(path).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            path = str(target)
        self._lock = Lock()
        self._closed = False
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._connection.row_factory = sqlite3.Row
        with self._access(write=True):
            # Keep the existing schema so previously recorded runs remain readable.
            self._connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, command TEXT NOT NULL, origin TEXT NOT NULL,
                invocation TEXT, argv TEXT NOT NULL, environment TEXT NOT NULL, options TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                returncode INTEGER, summary TEXT, error TEXT
            )""")

    @contextmanager
    def _access(self, *, write: bool = False):
        with self._lock:
            try:
                if write:
                    with self._connection:
                        yield
                else:
                    yield
            except sqlite3.Error as exc:
                raise RepoError(f"Could not access run metadata: {exc}") from exc

    def create_run(
        self,
        command: str,
        *,
        origin: str,
        invocation: str | None = None,
        argv=(),
        environment=None,
        options=None,
    ) -> RunRecord:
        record = RunRecord(
            id=str(uuid4()),
            command=command,
            origin=origin,
            invocation=invocation,
            argv=list(argv),
            environment=environment or {},
            options=options or {},
            started_at=timestamp(),
            status="starting",
        )
        with self._access(write=True):
            self._connection.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.id,
                    command,
                    origin,
                    invocation,
                    json.dumps(record.argv),
                    json.dumps(record.environment),
                    json.dumps(record.options),
                    record.started_at,
                    None,
                    "starting",
                    None,
                    None,
                    None,
                ),
            )
        return record

    def update_run(
        self,
        record_id: str,
        *,
        status: str,
        returncode: int | None = None,
        summary: dict | None = None,
        error: str | None = None,
    ) -> RunRecord:
        finished = None if status in {"running", "starting"} else timestamp()
        with self._access(write=True):
            self._connection.execute(
                "UPDATE runs SET status=?, returncode=?, finished_at=?, summary=?, error=? WHERE id=?",
                (status, returncode, finished, json.dumps(summary), error, record_id),
            )
        return self.get_run(record_id)

    @staticmethod
    def _decode(row) -> RunRecord:
        record = dict(row)
        for field in ("argv", "environment", "options", "summary"):
            record[field] = (
                json.loads(record[field]) if record[field] is not None else None
            )
        return RunRecord.model_validate(record)

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with self._access():
            rows = self._connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._decode(row) for row in rows]

    def get_run(self, record_id: str) -> RunRecord:
        with self._access():
            row = self._connection.execute(
                "SELECT * FROM runs WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            return self._decode(row)

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True
