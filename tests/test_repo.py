import json
import sqlite3

from molt_ui.repo import Repo


def test_repo_reads_the_existing_database_schema_and_preserves_exact_values(tmp_path):
    path = tmp_path / "existing.sqlite3"
    # This fixture uses the schema from before the repository refactor.
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE runs (
            id TEXT PRIMARY KEY, command TEXT NOT NULL, origin TEXT NOT NULL,
            invocation TEXT, argv TEXT NOT NULL, environment TEXT NOT NULL, options TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
            returncode INTEGER, summary TEXT, error TEXT
        )""")
        connection.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "existing",
                "fetch",
                "command",
                "molt fetch --direct-copy=true",
                json.dumps(["molt", "fetch", "--direct-copy=true"]),
                json.dumps({"MOLT_SOURCE": "postgres://user:exact-password@source/db"}),
                json.dumps({"direct-copy": True}),
                "2026-11-09T12:00:00+00:00",
                "2026-11-09T12:01:00+00:00",
                "succeeded",
                0,
                json.dumps({"exported": 200}),
                None,
            ),
        )
    repo = Repo(str(path))
    record = repo.get_run("existing")
    assert (
        record.environment["MOLT_SOURCE"] == "postgres://user:exact-password@source/db"
    )
    assert record.argv == ["molt", "fetch", "--direct-copy=true"]
    assert record.status == "succeeded"
    assert record.summary["exported"] == 200
    new = repo.create_run("verify", origin="help", argv=["molt", "verify", "--help"])
    updated = repo.update_run(
        new.id, status="failed", returncode=2, error="example failure"
    )
    assert updated.finished_at is not None
    assert updated.returncode == 2
    assert updated.error == "example failure"
    assert len(repo.list_runs()) == 2
    repo.close()
    reopened = Repo(str(path))
    assert reopened.get_run("existing") == record
    assert reopened.get_run(new.id) == updated
    reopened.close()
