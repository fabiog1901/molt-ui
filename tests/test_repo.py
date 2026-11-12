import json
import sqlite3
import pytest

from molt_ui.repo import Repo
from molt_ui.repo.repo import RepoConflict


def test_repo_initializes_schema_and_reopens_exact_run_values(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    repo = Repo(path)
    record = repo.create_run(
        "fetch", origin="command", invocation="molt fetch --direct-copy=true",
        argv=["molt", "fetch", "--direct-copy=true"],
        environment={"MOLT_SOURCE": "postgres://user:exact-password@source/db"},
        options={"direct-copy": True}, log_name="fetch-2026-11-09T12.00.00Z.log",
    )
    record = repo.update_run(record.id, status="succeeded", returncode=0, summary={"exported": 200})
    assert record.id == "2026-11-09T12.00.00Z"
    assert record.environment["MOLT_SOURCE"] == "postgres://user:exact-password@source/db"
    assert record.argv == ["molt", "fetch", "--direct-copy=true"]
    assert record.options == {"direct-copy": True}
    assert record.summary["exported"] == 200
    new = repo.create_run("verify", origin="help", argv=["molt", "verify", "--help"])
    updated = repo.update_run(new.id, status="failed", returncode=2, error="example failure")
    assert updated.finished_at is not None
    assert updated.returncode == 2
    assert updated.error == "example failure"
    assert len(repo.list_runs()) == 2
    repo.close()
    reopened = Repo(path)
    assert reopened.get_run(record.id) == record
    assert reopened.get_run(new.id) == updated
    reopened.close()


def test_history_uses_raw_timestamp_primary_key_without_a_separate_start_column():
    repo = Repo()
    try:
        later = repo.create_run('verify', origin='command', log_name='verify-2026-11-12T17.50.58Z.log')
        earlier = repo.create_run('fetch', origin='command', log_name='fetch-2026-11-12T16.00.00Z.log')
        assert [record.id for record in repo.list_runs()] == [later.id, earlier.id]
        columns = {row['name']: row for row in repo._connection.execute('PRAGMA table_info(runs)')}
        assert columns['id']['type'] == 'TIMESTAMP'
        assert columns['id']['pk'] == 1
        assert 'started_at' not in columns
        assert 'created_at' not in columns
        assert all(row['origin'] == 'pk' for row in repo._connection.execute('PRAGMA index_list(runs)'))
        assert 'started_at' not in later.model_dump()
    finally:
        repo.close()


def test_catalog_payload_version_and_timestamp_roundtrip(command_catalog, tmp_path):
    from datetime import datetime

    path = str(tmp_path / "catalog.sqlite3")
    repo = Repo(path)
    assert repo.get_catalog() is None
    saved = repo.save_catalog("molt version v1", command_catalog)
    datetime.strptime(saved.generated_at, '%Y-%m-%dT%H.%M.%SZ')
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


def test_recovery_handles_abandoned_jobs_and_preserves_completed_records():
    from molt_ui.molt_process import MoltProcess

    repo = Repo()
    try:
        abandoned = repo.create_run("fetch", origin="command")
        completed = repo.create_run("verify", origin="command")
        completed = repo.update_run(completed.id, status="failed", returncode=2, error="original error")
        foreign = repo.create_run("fetch", origin="command")
        foreign = repo.update_run(foreign.id, status="running")
        with repo._access(write=True):
            repo._connection.execute(
                "UPDATE runs SET owner_pid=-1 WHERE id=?", (abandoned.id,)
            )
            repo._connection.execute(
                "UPDATE runs SET owner_host=? WHERE id=?", ("another-host", foreign.id)
            )
        assert repo.recover_abandoned_runs(MoltProcess.is_owner_alive) == 1
        recovered = repo.get_run(abandoned.id)
        assert recovered.status == "interrupted"
        assert recovered.finished_at
        assert recovered.returncode is None
        assert repo.get_run(completed.id) == completed
        assert repo.get_run(foreign.id) == foreign
        assert repo.recover_abandoned_runs(MoltProcess.is_owner_alive) == 0
        assert repo.get_run(abandoned.id) == recovered
    finally:
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


def test_database_readiness_is_logged_on_initialization_and_reopen(tmp_path, caplog):
    import logging

    path = str(tmp_path / "events.sqlite3")
    with caplog.at_level(logging.INFO, logger="molt_ui.repo.repo"):
        for _ in range(2):
            caplog.clear()
            repo = Repo(path)
            repo.close()
            assert f"Opening SQLite database at {path}" in caplog.text
            assert f"SQLite database ready at {path}" in caplog.text


def test_clearing_history_removes_all_records_and_preserves_catalog(command_catalog, tmp_path):
    import pytest

    database = str(tmp_path / "clear-history.sqlite3")
    repo = Repo(database)
    catalog = repo.save_catalog("v1", command_catalog)
    records = [repo.create_run("fetch", origin="command") for _ in range(65)]
    assert len(repo.list_runs()) == 50
    assert repo.clear_runs() == 65
    assert repo.list_runs() == []
    assert repo.get_catalog() == catalog
    assert repo.clear_runs() == 0
    with pytest.raises(KeyError):
        repo.get_run(records[0].id)
    repo.close()
    repo = Repo(database)
    assert repo.list_runs() == []
    assert repo.get_catalog() == catalog
    repo.close()


def test_timestamp_keys_reject_duplicates_without_overwriting_history(monkeypatch):
    monkeypatch.setattr('molt_ui.repo.repo.timestamp', lambda: '2026-11-12T17.50.58Z')
    repo = Repo()
    try:
        original = repo.create_run('verify', origin='command')
        assert original.id == '2026-11-12T17.50.58Z'
        with pytest.raises(RepoConflict, match='Duplicate timestamps are not allowed'):
            repo.create_run('fetch', origin='command')
        with pytest.raises(RepoConflict, match='Duplicate timestamps are not allowed'):
            repo.create_run('verify', origin='import', log_name='verify-2026-11-12T17.50.58Z.log')
        assert repo.list_runs() == [original]
    finally:
        repo.close()


def test_log_timestamp_rekeys_saved_metrics_and_survives_restart(tmp_path):
    database = str(tmp_path / 'timestamp.sqlite3')
    path = tmp_path / 'verify-2026-11-12T17.50.58Z.log'
    path.write_text('saved output\n')
    repo = Repo(database)
    record = repo.create_run('verify', origin='command')
    repo.save_metrics(record.id, {'status': 'complete'}, {'timestamp': 10, 'values': {}})
    updated = repo.update_run(record.id, status='succeeded', returncode=0, log_file=str(path))
    assert updated.id == '2026-11-12T17.50.58Z'
    with pytest.raises(KeyError):
        repo.get_run(record.id)
    assert repo.get_metrics(updated.id)[1] == [{'timestamp': 10, 'values': {}}]
    assert repo.get_metrics(record.id) == (None, [])
    assert repo.get_run_output(updated.id).events[0].text == 'saved output'
    assert repo._connection.execute('PRAGMA foreign_key_check').fetchall() == []
    repo.close()
    reopened = Repo(database)
    try:
        assert reopened.get_run(updated.id) == updated
        assert reopened.get_metrics(updated.id)[0] == {'status': 'complete'}
        reopened.delete_run(updated.id)
        assert reopened.get_metrics(updated.id) == (None, [])
    finally:
        reopened.close()


def test_duplicate_log_timestamp_rolls_back_run_and_metric_updates(tmp_path):
    repo = Repo()
    try:
        original = repo.create_run('verify', origin='command', log_name='verify-2026-11-12T17.50.58Z.log')
        original = repo.update_run(original.id, status='succeeded', returncode=0)
        attempt = repo.create_run('verify', origin='command')
        frame = {'timestamp': 10, 'values': {}}
        repo.save_metrics(attempt.id, {'status': 'collecting'}, frame)
        with pytest.raises(RepoConflict):
            repo.update_run(attempt.id, status='failed', returncode=1,
                            log_file=str(tmp_path / 'verify-2026-11-12T17.50.58Z.log'))
        assert repo.get_run(original.id) == original
        assert repo.get_run(attempt.id) == attempt
        assert repo.get_metrics(attempt.id)[1] == [frame]
        assert repo.get_metrics(original.id) == (None, [])
    finally:
        repo.close()


def test_completion_and_output_changes_roll_back_together():
    repo = Repo()
    try:
        record = repo.create_run('fetch', origin='command')
        repo.save_metrics(record.id, {'status': 'collecting'}, {'timestamp': 1, 'values': {}})

        class FailedOutput:
            def __iter__(self):
                raise OSError('capture is unreadable')

        with pytest.raises(OSError, match='capture is unreadable'):
            repo.update_run(record.id, status='succeeded', output=FailedOutput())
        assert repo.get_run(record.id) == record
        assert repo.get_metrics(record.id)[0]['status'] == 'collecting'
    finally:
        repo.close()
