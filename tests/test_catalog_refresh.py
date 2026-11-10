"""Startup synchronization keeps the catalog and its SQLite version in step."""

from hashlib import sha256
from unittest.mock import Mock, call

import pytest

from molt_ui import bootstrap, catalog_update
from molt_ui.config import Settings
from molt_ui.core import catalog
from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandResult
from molt_ui.repo import Repo


def fake_process(version="molt version v1", default="info"):
    process = Mock()

    def run(arguments):
        text = version if arguments == ["--version"] else (
            f'Flags:\n      --logging string       Log level (default "{default}")\n'
        )
        return CommandResult(stdout=text, stderr="", returncode=0)

    process.run.side_effect = run
    return process


@pytest.fixture
def resource(monkeypatch, tmp_path):
    output = tmp_path / "resources/command_catalog.json"
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(catalog.catalog_path().read_bytes())
    monkeypatch.setattr(catalog_update, "catalog_path", lambda: output)
    monkeypatch.setattr(catalog, "catalog_path", lambda: output)
    catalog.load_catalog.cache_clear()
    yield output
    catalog.load_catalog.cache_clear()


def test_first_start_refreshes_and_records_version_then_only_checks_version(resource, tmp_path):
    database = str(tmp_path / "metadata.sqlite3")
    repo = Repo(database)
    process = fake_process()
    assert repo.get_catalog_state() is None
    assert catalog_update.refresh_catalog(process, repo) is True
    assert len(process.run.call_args_list) == 6
    state = repo.get_catalog_state()
    assert state.version == "molt version v1"
    assert state.sha256 == sha256(resource.read_bytes()).hexdigest()
    repo.close()
    # The comparison survives restarts, rather than being an in-memory flag.
    repo = Repo(database)
    process.run.reset_mock()
    assert catalog_update.refresh_catalog(process, repo) is False
    process.run.assert_called_once_with(["--version"])
    repo.close()


def test_version_change_replaces_catalog_and_invalidates_loaded_cache(resource):
    repo = Repo()
    catalog_update.refresh_catalog(fake_process(), repo)
    before = catalog.load_catalog()
    assert before.commands[0].options[0].default == "info"
    assert catalog_update.refresh_catalog(fake_process("molt version v2", "debug"), repo)
    assert repo.get_catalog_state().version == "molt version v2"
    assert catalog.load_catalog().commands[0].options[0].default == "debug"
    repo.close()


@pytest.mark.parametrize("damage", ["missing", "invalid", "replaced"])
def test_same_version_repairs_missing_or_changed_catalog(resource, damage):
    repo = Repo()
    catalog_update.refresh_catalog(fake_process(), repo)
    if damage == "missing":
        resource.unlink()
    elif damage == "invalid":
        resource.write_text("broken JSON")
    else:
        resource.write_text(resource.read_text().replace("info", "debug"))
    process = fake_process()
    assert catalog_update.refresh_catalog(process, repo)
    assert len(process.run.call_args_list) == 6
    assert catalog.load_catalog().commands[0].options[0].default == "info"
    repo.close()


@pytest.mark.parametrize("failure", ["help", "format", "write"])
def test_failed_refresh_preserves_catalog_and_version_for_retry(resource, monkeypatch, failure):
    repo = Repo()
    catalog_update.refresh_catalog(fake_process(), repo)
    before, state = resource.read_bytes(), repo.get_catalog_state()
    process = fake_process("molt version v2", "debug")
    if failure == "help":
        process.run.side_effect = [
            CommandResult(stdout="molt version v2", stderr="", returncode=0),
            CommandResult(stdout="", stderr="help failed", returncode=1),
        ]
    elif failure == "format":
        process.run.side_effect = [
            CommandResult(stdout="molt version v2", stderr="", returncode=0),
            CommandResult(stdout="unrecognized help", stderr="", returncode=0),
        ]
    else:
        def fail_replace(*args):
            raise PermissionError("read-only resource")
        monkeypatch.setattr(catalog_update.os, "replace", fail_replace)
    with pytest.raises((MoltError, ValueError, OSError)):
        catalog_update.refresh_catalog(process, repo)
    assert resource.read_bytes() == before
    assert repo.get_catalog_state() == state
    assert not list(resource.parent.glob(".command-catalog-*"))
    repo.close()


@pytest.mark.parametrize("result", [
    CommandResult(stdout="", stderr="version failed", returncode=2),
    CommandResult(stdout="\n", stderr="", returncode=0),
])
def test_failed_version_check_never_changes_catalog_or_database(resource, result):
    repo = Repo()
    before = resource.read_bytes()
    process = Mock()
    process.run.return_value = result
    with pytest.raises(MoltError):
        catalog_update.refresh_catalog(process, repo)
    process.run.assert_called_once_with(["--version"])
    assert repo.get_catalog_state() is None
    assert resource.read_bytes() == before
    repo.close()


def test_version_can_be_reported_on_stderr(resource):
    process = fake_process()
    run = process.run.side_effect
    process.run.side_effect = lambda args: (
        CommandResult(stdout="", stderr="molt version v1\n", returncode=0)
        if args == ["--version"] else run(args)
    )
    repo = Repo()
    assert catalog_update.refresh_catalog(process, repo)
    assert repo.get_catalog_state().version == "molt version v1"
    repo.close()


def test_startup_uses_configured_binary_and_same_database(resource, monkeypatch, tmp_path):
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
    assert repo.get_catalog_state().version == "molt version v1"
    repo.close()


def test_startup_warning_keeps_existing_catalog_available(resource, monkeypatch, tmp_path, caplog):
    process = Mock()
    process.run.side_effect = MoltError("binary unavailable")
    monkeypatch.setattr(bootstrap, "MoltProcess", Mock(return_value=process))
    settings = Settings(executable="/missing/molt", database=str(tmp_path / "startup.sqlite3"))
    service = bootstrap.create_service(settings)
    assert len(service.commands()) == 5
    assert "keeping the existing catalog" in caplog.text
    assert "binary unavailable" in caplog.text
    service.close()
