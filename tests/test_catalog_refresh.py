"""Startup loads SQLite's catalog and refreshes its payload and version together."""

from io import StringIO
import sqlite3
from unittest.mock import Mock, call

import pytest

from molt_ui import bootstrap, catalog_update
from molt_ui.config import Settings
from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandResult
from molt_ui.repo import Repo
from molt_ui.repo.repo import RepoError


def fake_process(version="molt version v1", default="info"):
    process = Mock()

    def run(arguments):
        if arguments == ["--version"]:
            text = version
        elif arguments == ["--help"]:
            text = "Available Commands:\n  fetch   Fetch\n  verify   Verify\n  convert   Convert\n\nFlags:\n"
        elif arguments == ["convert", "--help"]:
            text = "Available Commands:\n  postgres   PostgreSQL\n  mysql   MySQL\n  oracle   Oracle\n\nFlags:\n"
        else:
            text = f'Flags:\n      --logging string       Log level (default "{default}")\n'
        return CommandResult(stdout=text, stderr="", returncode=0)

    process.run.side_effect = run
    return process


def test_first_start_saves_catalog_and_restart_only_checks_version(tmp_path):
    database = str(tmp_path / "metadata.sqlite3")
    repo = Repo(database)
    process = fake_process()
    assert repo.get_catalog() is None
    generated = catalog_update.refresh_catalog(process, repo)
    assert len(process.run.call_args_list) == 8
    saved = repo.get_catalog()
    assert saved.version == "molt version v1"
    assert saved.catalog == generated
    assert saved.generated_at
    repo.close()
    repo = Repo(database)
    process.run.reset_mock()
    assert catalog_update.refresh_catalog(process, repo) == generated
    process.run.assert_called_once_with(["--version"])
    assert repo.get_catalog() == saved
    repo.close()


def test_version_change_replaces_saved_catalog_without_mutating_previous_instance():
    repo = Repo()
    first = catalog_update.refresh_catalog(fake_process(), repo)
    refreshed = catalog_update.refresh_catalog(fake_process("molt version v2", "debug"), repo)
    assert repo.get_catalog().version == "molt version v2"
    assert refreshed.commands[0].options[0].default == "debug"
    assert first.commands[0].options[0].default == "info"
    repo.close()


def test_invalid_saved_payload_is_regenerated_even_for_same_version(tmp_path):
    path = str(tmp_path / "metadata.sqlite3")
    repo = Repo(path)
    catalog_update.refresh_catalog(fake_process(), repo)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE command_catalog SET payload='broken JSON'")
    process = fake_process()
    result = catalog_update.refresh_catalog(process, repo)
    assert len(process.run.call_args_list) == 8
    assert repo.get_catalog().catalog == result
    repo.close()


@pytest.mark.parametrize("failure", ["help", "format", "write"])
def test_failed_refresh_keeps_saved_catalog_and_version_then_retries(monkeypatch, failure, caplog):
    repo = Repo()
    first = catalog_update.refresh_catalog(fake_process(), repo)
    saved = repo.get_catalog()
    process = fake_process("molt version v2", "debug")
    with monkeypatch.context() as patcher:
        if failure in {"help", "format"}:
            process.run.side_effect = [
                CommandResult(stdout="molt version v2", stderr="", returncode=0),
                CommandResult(stdout="unrecognized help", stderr="failed", returncode=1 if failure == "help" else 0),
            ]
        else:
            patcher.setattr(repo, "save_catalog", Mock(side_effect=RepoError("database write failed")))
        assert catalog_update.refresh_catalog(process, repo) == first
    assert repo.get_catalog() == saved
    assert "using the saved catalog" in caplog.text
    retried = catalog_update.refresh_catalog(fake_process("molt version v2", "debug"), repo)
    assert repo.get_catalog().version == "molt version v2"
    assert retried.commands[0].options[0].default == "debug"
    repo.close()


@pytest.mark.parametrize("result", [
    CommandResult(stdout="", stderr="version failed", returncode=2),
    CommandResult(stdout="\n", stderr="", returncode=0),
    MoltError("binary unavailable"),
])
def test_first_start_reports_missing_catalog_when_binary_is_unavailable(result):
    repo = Repo()
    process = Mock()
    if isinstance(result, Exception):
        process.run.side_effect = result
    else:
        process.run.return_value = result
    with pytest.raises(MoltError, match="No usable command catalog is stored in SQLite"):
        catalog_update.refresh_catalog(process, repo)
    process.run.assert_called_once_with(["--version"])
    assert repo.get_catalog() is None
    repo.close()


def test_version_can_be_reported_on_stderr():
    process = fake_process()
    run = process.run.side_effect
    process.run.side_effect = lambda args: (
        CommandResult(stdout="", stderr="molt version v1\n", returncode=0)
        if args == ["--version"] else run(args)
    )
    repo = Repo()
    result = catalog_update.refresh_catalog(process, repo)
    assert repo.get_catalog().version == "molt version v1"
    assert repo.get_catalog().catalog == result
    repo.close()


def test_startup_injects_catalog_from_configured_binary_and_database(monkeypatch, tmp_path):
    process = fake_process()
    factory = Mock(return_value=process)
    monkeypatch.setattr(bootstrap, "MoltProcess", factory)
    settings = Settings(executable="/custom/molt", database=str(tmp_path / "startup.sqlite3"))
    service = bootstrap.create_service(settings)
    assert factory.call_args.args == ("/custom/molt",)
    assert process.run.call_args_list[0] == call(["--version"])
    assert service.commands()[0].options[0].default == "info"
    service.close()
    repo = Repo(settings.database)
    assert repo.get_catalog().version == "molt version v1"
    repo.close()


def test_restart_uses_sqlite_catalog_when_binary_is_unavailable(command_catalog, monkeypatch, tmp_path, caplog):
    from fastapi.testclient import TestClient
    from molt_ui.frontends.api.app import create_app

    settings = Settings(executable="/missing/molt", database=str(tmp_path / "startup.sqlite3"))
    repo = Repo(settings.database)
    repo.save_catalog("molt version v1", command_catalog)
    repo.close()
    process = Mock()
    process.run.side_effect = MoltError("binary unavailable")
    monkeypatch.setattr(bootstrap, "MoltProcess", Mock(return_value=process))
    service = bootstrap.create_service(settings)
    assert service.commands() == command_catalog.commands
    assert "using the saved catalog" in caplog.text
    assert "binary unavailable" in caplog.text
    with TestClient(create_app(service)) as client:
        assert client.get("/api/commands").status_code == 200


def test_first_launch_without_binary_keeps_imports_and_history_available(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from molt_ui.frontends.api.app import create_app

    process = Mock()
    process.run.side_effect = MoltError("binary unavailable")
    monkeypatch.setattr(bootstrap, "MoltProcess", Mock(return_value=process))
    settings = Settings(executable="/missing/molt", database=str(tmp_path / "startup.sqlite3"))
    service = bootstrap.create_service(settings)
    with TestClient(create_app(service)) as client:
        response = client.get("/api/commands")
        assert response.status_code == 503
        assert "MOLT_EXECUTABLE" in response.json()["detail"]
        assert client.get("/").status_code == 200
        assert client.get("/api/history").json() == []
        assert service.import_log(StringIO("sample output\n")).status == "imported"
