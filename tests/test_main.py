from unittest.mock import Mock

import pytest

from molt_ui.main import main


@pytest.mark.parametrize(
    ("argv", "host", "port", "reload"),
    [
        ([], "127.0.0.1", 8000, False),
        (["--host", "0.0.0.0", "--port", "8080"], "0.0.0.0", 8080, False),
        (["--reload"], "127.0.0.1", 8000, True),
        (["--host", "0.0.0.0", "--port", "8080", "--reload"], "0.0.0.0", 8080, True),
    ],
)
def test_cli_starts_fastapi(monkeypatch, argv, host, port, reload):
    run = Mock()
    monkeypatch.setattr("molt_ui.main.uvicorn.run", run)
    main(argv)
    run.assert_called_once_with("molt_ui.api.app:app", host=host, port=port, reload=reload)


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--log-level=debug", "--root-path=/molt"],
        ["--log-level", "debug", "--root-path", "/molt"],
    ],
)
def test_cli_forwards_additional_uvicorn_options(monkeypatch, extra_args):
    run = Mock()
    monkeypatch.setattr("molt_ui.main.uvicorn.run", run)
    main(["--port", "8080", "--reload", *extra_args])
    run.assert_called_once_with(
        "molt_ui.api.app:app", host="127.0.0.1", port=8080, reload=True,
        log_level="debug", root_path="/molt",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["--port", "0"],
        ["--port", "65536"],
        ["--port", "bad"],
        ["--unknown"],
        ["--log-level", "--another-option=debug"],
        ["unexpected"],
        ["--=value"],
    ],
)
def test_cli_exits_without_starting_server(monkeypatch, argv):
    run = Mock()
    monkeypatch.setattr("molt_ui.main.uvicorn.run", run)
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == (0 if argv == ["--help"] else 2)
    run.assert_not_called()


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_drop_db_recreates_schema_at_configured_path(
    monkeypatch, tmp_path, configured, existing
):
    from molt_ui.config import Settings
    from molt_ui.repo import Repo

    monkeypatch.chdir(tmp_path)
    if configured:
        database = tmp_path / "custom" / "history.sqlite3"
        monkeypatch.setenv("MOLT_DATABASE", str(database))
    else:
        database = tmp_path / ".data" / "molt-ui.sqlite3"
        monkeypatch.delenv("MOLT_DATABASE", raising=False)
    if existing:
        repo = Repo(str(database))
        repo.create_run("fetch", origin="import")
        repo.close()
        for suffix in ("-wal", "-shm", "-journal"):
            database.with_name(database.name + suffix).write_bytes(b"stale data")

    def run(app, **options):
        assert app == "molt_ui.api.app:app"
        assert options == {"host": "127.0.0.1", "port": 8000, "reload": True}
        assert Settings.from_environment().database == str(database)
        assert not database.exists()
        for suffix in ("-wal", "-shm", "-journal"):
            assert not database.with_name(database.name + suffix).exists()
        repo = Repo(str(database))
        assert repo.list_runs() == []
        saved = repo.create_run("fetch", origin="import")
        repo.close()
        # A new service on reload reopens the same database without dropping it.
        repo = Repo(str(database))
        assert repo.get_run(saved.id) == saved
        repo.close()

    monkeypatch.setattr("molt_ui.main.uvicorn.run", run)
    main(["--drop-db", "--reload"])
    assert database.exists()


def test_drop_db_supports_in_memory_database(monkeypatch):
    monkeypatch.setenv("MOLT_DATABASE", ":memory:")
    run = Mock()
    monkeypatch.setattr("molt_ui.main.uvicorn.run", run)
    main(["--drop-db"])
    run.assert_called_once_with(
        "molt_ui.api.app:app", host="127.0.0.1", port=8000, reload=False
    )
