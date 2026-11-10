"""Exact local command metadata, persisted with Python's SQLite driver."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from uuid import uuid4


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunHistory:
    def __init__(self, path: str = ':memory:') -> None:
        if path != ':memory:':
            target = Path(path).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            path = str(target)
        self._lock = Lock()
        self._closed = False
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, command TEXT NOT NULL, origin TEXT NOT NULL,
            invocation TEXT, argv TEXT NOT NULL, environment TEXT NOT NULL, options TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
            returncode INTEGER, summary TEXT, error TEXT
        )''')
        self._connection.commit()

    def create(self, command: str, *, origin: str, invocation=None, argv=(), environment=None, options=None) -> dict:
        record = dict(id=str(uuid4()), command=command, origin=origin, invocation=invocation,
                      argv=list(argv), environment=environment or {}, options=options or {},
                      started_at=timestamp(), finished_at=None, status='starting', returncode=None, summary=None, error=None)
        with self._lock, self._connection:
            self._connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                record['id'], command, origin, invocation, json.dumps(record['argv']),
                json.dumps(record['environment']), json.dumps(record['options']), record['started_at'],
                None, 'starting', None, None, None,
            ))
        return record

    def update(self, record_id: str, state: dict, error: str | None = None) -> dict:
        status = state['status']
        finished = None if status in {'running', 'starting'} else timestamp()
        with self._lock, self._connection:
            self._connection.execute('UPDATE runs SET status=?, returncode=?, finished_at=?, summary=?, error=? WHERE id=?',
                                     (status, state.get('returncode'), finished, json.dumps(state.get('aggregation', {}).get('totals')), error, record_id))
        return self.get(record_id)

    @staticmethod
    def _decode(row) -> dict:
        record = dict(row)
        for field in ('argv', 'environment', 'options', 'summary'):
            record[field] = json.loads(record[field]) if record[field] is not None else None
        return record

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._connection.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT ?', (limit,)).fetchall()
            return [self._decode(row) for row in rows]

    def get(self, record_id: str) -> dict:
        with self._lock:
            row = self._connection.execute('SELECT * FROM runs WHERE id=?', (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            return self._decode(row)

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True
