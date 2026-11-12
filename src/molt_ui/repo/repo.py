"""SQLite persistence for application metadata; no execution or frontend policy."""

from contextlib import contextmanager
from datetime import datetime, timezone
from collections.abc import Callable, Iterable, Iterator
import json
import logging
import os
from pathlib import Path
import sqlite3
import socket
from threading import Lock
from uuid import uuid4

from molt_ui.core.logs import parse_line
from molt_ui.core.models import CatalogRecord, CommandCatalog, HistoryOutput, OutputEvent, RunRecord
from .output import iter_log_file, read_log_file


logger = logging.getLogger(__name__)


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
        logger.info("Opening SQLite database at %s", path)
        self._lock = Lock()
        self._closed = False
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._access(write=True):
            self._connection.execute("BEGIN")
            tables = {
                row["name"] for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            initializing = not ({"runs", "command_catalog"} & tables)
            changes = [f"created {name}" for name in ("runs", "command_catalog") if name not in tables]
            # Keep the existing schema so previously recorded runs remain readable.
            self._connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, command TEXT NOT NULL, origin TEXT NOT NULL,
                invocation TEXT, argv TEXT NOT NULL, environment TEXT NOT NULL, options TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                returncode INTEGER, summary TEXT, error TEXT, log_file TEXT
            )""")
            run_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(runs)")}
            if "log_file" not in run_columns:
                self._connection.execute("ALTER TABLE runs ADD COLUMN log_file TEXT")
                changes.append("added runs.log_file")
            for column, kind in (("owner_pid", "INTEGER"), ("owner_host", "TEXT")):
                if column not in run_columns:
                    self._connection.execute(f"ALTER TABLE runs ADD COLUMN {column} {kind}")
                    changes.append(f"added runs.{column}")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS run_output (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL, stream TEXT NOT NULL, text TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            )""")
            if "run_output" not in tables:
                changes.append("created run_output")
            columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(command_catalog)")
            }
            if "sha256" in columns:
                # The old table only held a file fingerprint, never a catalog.
                # Discard that obsolete marker; startup will populate the payload.
                changes.append("migrated command_catalog from file fingerprint to stored payload")
                self._connection.execute("DROP TABLE command_catalog")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS command_catalog (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version TEXT NOT NULL, payload TEXT NOT NULL, generated_at TEXT NOT NULL
            )""")
        # Report success only after the schema transaction has committed.
        if initializing:
            logger.info("Initialized SQLite database at %s (%s)", path, "; ".join(changes))
        else:
            if changes:
                logger.info("Updated SQLite schema at %s (%s)", path, "; ".join(changes))
            logger.info("Loaded existing SQLite database at %s", path)

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
                raise RepoError(f"Could not access application metadata: {exc}") from exc

    def get_catalog(self) -> CatalogRecord | None:
        with self._access():
            row = self._connection.execute(
                "SELECT version, payload, generated_at FROM command_catalog WHERE id = 1"
            ).fetchone()
            if row is None:
                return None
            try:
                return CatalogRecord(
                    version=row["version"],
                    catalog=CommandCatalog.model_validate_json(row["payload"]),
                    generated_at=row["generated_at"],
                )
            except ValueError as exc:
                raise RepoError("The saved command catalog is incompatible or invalid.") from exc

    def save_catalog(self, version: str, catalog: CommandCatalog) -> CatalogRecord:
        record = CatalogRecord(version=version, catalog=catalog, generated_at=timestamp())
        with self._access(write=True):
            self._connection.execute(
                """INSERT INTO command_catalog (id, version, payload, generated_at) VALUES (1, ?, ?, ?)
                   ON CONFLICT (id) DO UPDATE SET version=excluded.version,
                   payload=excluded.payload, generated_at=excluded.generated_at""",
                (record.version, catalog.model_dump_json(exclude_unset=True), record.generated_at),
            )
        return record

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
                """INSERT INTO runs (id, command, origin, invocation, argv, environment, options,
                   started_at, finished_at, status, returncode, summary, error, owner_pid, owner_host)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    os.getpid(),
                    socket.gethostname(),
                ),
            )
        return record

    def recover_abandoned_runs(self, is_owner_alive: Callable[[int | None, str | None], bool]) -> int:
        """Reconcile unfinished history without changing runs with a live owner."""
        with self._access(write=True):
            # Serialize recovery with other writers, including job completion.
            self._connection.execute("BEGIN IMMEDIATE")
            rows = self._connection.execute(
                "SELECT id, owner_pid, owner_host FROM runs WHERE status IN ('starting', 'running')"
            ).fetchall()
            abandoned = [row["id"] for row in rows
                         if not is_owner_alive(row["owner_pid"], row["owner_host"])]
            message = "The app stopped before recording Molt's exit status; the outcome is unknown."
            self._connection.executemany(
                """UPDATE runs SET status='interrupted', finished_at=?,
                   error=CASE WHEN error IS NULL OR error='' THEN ? ELSE error || char(10) || ? END
                   WHERE id=? AND status IN ('starting', 'running')""",
                ((timestamp(), message, message, record_id) for record_id in abandoned),
            )
        return len(abandoned)

    def update_run(
        self,
        record_id: str,
        *,
        status: str,
        returncode: int | None = None,
        summary: dict | None = None,
        error: str | None = None,
        log_file: str | None = None,
        output: Iterable[OutputEvent] | None = None,
    ) -> RunRecord:
        finished = None if status in {"running", "starting"} else timestamp()
        with self._access(write=True):
            if output is not None or log_file is not None:
                self._connection.execute("DELETE FROM run_output WHERE run_id=?", (record_id,))
            if output is not None and log_file is None:
                self._connection.executemany(
                    "INSERT INTO run_output (run_id, sequence, stream, text) VALUES (?,?,?,?)",
                    ((record_id, event.sequence, event.stream, event.text) for event in output),
                )
            self._connection.execute(
                """UPDATE runs SET status=?, returncode=?, finished_at=?, summary=?, error=?,
                   log_file=COALESCE(?, log_file) WHERE id=?""",
                (status, returncode, finished, json.dumps(summary), error, log_file, record_id),
            )
        return self.get_run(record_id)

    @staticmethod
    def _decode(row) -> RunRecord:
        record = dict(row)
        record.pop("owner_pid", None)
        record.pop("owner_host", None)
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

    def iter_run_output(self, record_id: str) -> Iterator[OutputEvent]:
        """Read the full saved output in order without loading it all into RAM."""
        record = self.get_run(record_id)
        if record.log_file:
            try:
                yield from iter_log_file(record.log_file)
            except OSError as exc:
                raise RepoError(f"Could not open saved log file {record.log_file}: {exc.strerror}") from exc
            return
        after = 0
        while True:
            with self._access():
                rows = self._connection.execute(
                    """SELECT sequence, stream, text FROM run_output
                       WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 1000""",
                    (record_id, after),
                ).fetchall()
            if not rows:
                return
            for row in rows:
                yield OutputEvent(**dict(row), data=parse_line(row["text"]))
            after = rows[-1]["sequence"]

    def get_run_output(self, record_id: str, *, before: int | None = None, limit: int = 2000) -> HistoryOutput:
        record = self.get_run(record_id)
        if record.log_file:
            try:
                return read_log_file(record.log_file, before=before, limit=limit)
            except OSError as exc:
                raise RepoError(f"Could not open saved log file {record.log_file}: {exc.strerror}") from exc
        with self._access():
            total = self._connection.execute(
                "SELECT COUNT(*) FROM run_output WHERE run_id=?", (record_id,)
            ).fetchone()[0]
            rows = self._connection.execute(
                """SELECT sequence, stream, text FROM run_output WHERE run_id=?
                   AND (? IS NULL OR sequence < ?) ORDER BY sequence DESC LIMIT ?""",
                (record_id, before, before, limit),
            ).fetchall()
        events = tuple(OutputEvent(**dict(row), data=parse_line(row["text"])) for row in reversed(rows))
        return HistoryOutput(
            source="captured", total=total, events=events,
            next_before=events[0].sequence if events and events[0].sequence > 1 else None,
        )

    def delete_run(self, record_id: str) -> int:
        with self._access(write=True):
            deleted = self._connection.execute("DELETE FROM runs WHERE id=?", (record_id,)).rowcount
            if not deleted:
                raise KeyError(record_id)
        logger.info("Deleted saved run %s", record_id)
        return deleted

    def clear_runs(self) -> int:
        with self._access(write=True):
            deleted = self._connection.execute("DELETE FROM runs").rowcount
        logger.info("Cleared saved run history (%d records)", deleted)
        return deleted

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
