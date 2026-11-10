from unittest.mock import Mock

from molt_ui import config
from molt_ui.bootstrap import create_service
from molt_ui.core.service import MoltService
from molt_ui.repo import Repo


def test_help_is_a_named_operation_and_executable_is_configurable(command_catalog,
    monkeypatch, tmp_path
):
    process = Mock()
    service = MoltService(process, Repo(), catalog=command_catalog)
    service.help()
    process.run.assert_called_once_with(["--help"])
    service.close()
    local_binary = tmp_path / "molt" / "molt"
    monkeypatch.setattr(config, "LOCAL_EXECUTABLE", local_binary)
    monkeypatch.delenv("MOLT_EXECUTABLE", raising=False)
    assert config.Settings.from_environment().executable == "molt"
    local_binary.parent.mkdir()
    local_binary.touch()
    monkeypatch.chdir(tmp_path.parent)
    assert config.Settings.from_environment().executable == str(local_binary)
    monkeypatch.setenv("MOLT_EXECUTABLE", "/custom/molt")
    settings = config.Settings.from_environment()
    assert settings.executable == "/custom/molt"
    instance = create_service(settings)
    assert isinstance(instance, MoltService)
    instance.close()
