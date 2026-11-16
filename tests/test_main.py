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
