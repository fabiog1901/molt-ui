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


def test_catalog_payload_version_and_timestamp_roundtrip(command_catalog, tmp_path):
    from datetime import datetime

    path = str(tmp_path / "catalog.sqlite3")
    repo = Repo(path)
    assert repo.get_catalog() is None
    saved = repo.save_catalog("molt version v1", command_catalog)
    datetime.fromisoformat(saved.generated_at)
    repo.close()
    repo = Repo(path)
    assert repo.get_catalog() == saved
    with sqlite3.connect(path) as connection:
        version, payload, generated_at = connection.execute(
            "SELECT version, payload, generated_at FROM command_catalog"
        ).fetchone()
    assert version == saved.version
    assert json.loads(payload) == command_catalog.model_dump(mode="json", exclude_unset=True)
    assert generated_at == saved.generated_at
    repo.close()


def test_failed_catalog_write_rolls_back_payload_and_version(command_catalog, tmp_path):
    import pytest
    from molt_ui.repo.repo import RepoError

    path = str(tmp_path / "catalog.sqlite3")
    repo = Repo(path)
    saved = repo.save_catalog("v1", command_catalog)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER reject_catalog BEFORE UPDATE ON command_catalog
            BEGIN SELECT RAISE(ABORT, 'write failed'); END""")
    changed = command_catalog.model_copy(update={"commands": command_catalog.commands[:1]})
    with pytest.raises(RepoError, match="write failed"):
        repo.save_catalog("v2", changed)
    assert repo.get_catalog() == saved
    repo.close()


def test_invalid_stored_catalog_is_reported(command_catalog, tmp_path):
    import pytest
    from molt_ui.repo.repo import RepoError

    path = str(tmp_path / "catalog.sqlite3")
    repo = Repo(path)
    repo.save_catalog("v1", command_catalog)
    raw = command_catalog.model_dump(mode="json")
    raw["commands"][0]["options"][0]["kind"] = "unsupported"
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE command_catalog SET payload=?", (json.dumps(raw),))
    with pytest.raises(RepoError, match="incompatible or invalid"):
        repo.get_catalog()
    repo.close()


def test_old_catalog_fingerprint_migrates_without_losing_runs(command_catalog, tmp_path):
    path = str(tmp_path / "legacy.sqlite3")
    repo = Repo(path)
    run = repo.create_run("fetch", origin="command", invocation="molt fetch")
    repo.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE command_catalog")
        connection.execute("""CREATE TABLE command_catalog (
            id INTEGER PRIMARY KEY CHECK (id = 1), version TEXT NOT NULL, sha256 TEXT NOT NULL
        )""")
        connection.execute("INSERT INTO command_catalog VALUES (1, 'v1', 'old-file-fingerprint')")
    repo = Repo(path)
    assert repo.get_run(run.id) == run
    assert repo.get_catalog() is None
    saved = repo.save_catalog("v1", command_catalog)
    assert repo.get_catalog() == saved
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(command_catalog)")}
    assert columns == {"id", "version", "payload", "generated_at"}
    repo.close()


def test_database_lifecycle_logs_distinguish_initialization_and_existing_schema(tmp_path, caplog):
    import logging

    path = str(tmp_path / "events.sqlite3")
    with caplog.at_level(logging.INFO, logger="molt_ui.repo.repo"):
        repo = Repo(path)
        repo.close()
        assert f"Opening SQLite database at {path}" in caplog.text
        assert f"Initialized SQLite database at {path}" in caplog.text
        assert "created runs; created command_catalog" in caplog.text
        caplog.clear()
        repo = Repo(path)
        repo.close()
        assert f"Loaded existing SQLite database at {path}" in caplog.text
        assert "Initialized" not in caplog.text
        assert "Updated SQLite schema" not in caplog.text


def test_schema_upgrade_is_logged_and_preserves_run_values(tmp_path, caplog):
    import logging

    path = str(tmp_path / "upgrade.sqlite3")
    repo = Repo(path)
    record = repo.create_run("fetch", origin="command", invocation="sensitive-command-value")
    repo.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE command_catalog")
        connection.execute("""CREATE TABLE command_catalog (
            id INTEGER PRIMARY KEY, version TEXT NOT NULL, sha256 TEXT NOT NULL
        )""")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="molt_ui.repo.repo"):
        repo = Repo(path)
        assert repo.get_run(record.id) == record
        repo.close()
    assert f"Updated SQLite schema at {path}" in caplog.text
    assert "migrated command_catalog from file fingerprint to stored payload" in caplog.text
    assert "sensitive-command-value" not in caplog.text
