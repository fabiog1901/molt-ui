import subprocess
from unittest.mock import Mock

import pytest

from molt_ui import file_picker


@pytest.fixture
def mac_picker(monkeypatch):
    monkeypatch.setattr(file_picker.sys, "platform", "darwin")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "\n", ""))
    monkeypatch.setattr(file_picker.subprocess, "run", run)
    return run


def test_mac_picker_preserves_original_path_and_whitespace(mac_picker, tmp_path):
    selected = tmp_path / "my transformations 日本語.json "
    selected.write_text("{}")
    mac_picker.return_value.stdout = str(selected) + "\n"
    assert file_picker.choose_file() == str(selected)
    args, kwargs = mac_picker.call_args
    assert args[0][0] == "/usr/bin/osascript"
    assert "POSIX path" in args[0][2]
    assert kwargs["timeout"] == 300


def test_mac_picker_cancellation(mac_picker):
    assert file_picker.choose_file() is None


@pytest.mark.parametrize("path", ["relative.json\n", "/missing/file.json\n"])
def test_picker_rejects_invalid_selection(mac_picker, path):
    mac_picker.return_value.stdout = path
    with pytest.raises(RuntimeError, match="no longer available"):
        file_picker.choose_file()


@pytest.mark.parametrize("failure", [
    OSError("missing osascript"),
    subprocess.TimeoutExpired("osascript", 300),
    None,
])
def test_picker_errors_release_the_dialog_lock(mac_picker, failure):
    mac_picker.side_effect = failure
    mac_picker.return_value.returncode = 1
    with pytest.raises(RuntimeError, match="file picker"):
        file_picker.choose_file()
    mac_picker.side_effect = None
    mac_picker.return_value.returncode = 0
    assert file_picker.choose_file() is None


def test_concurrent_dialogs_are_rejected(mac_picker):
    with file_picker._picker_lock:
        with pytest.raises(RuntimeError, match="already open"):
            file_picker.choose_file()
    mac_picker.assert_not_called()


def test_other_desktops_run_tk_in_a_separate_process(monkeypatch, mac_picker, tmp_path):
    monkeypatch.setattr(file_picker.sys, "platform", "linux")
    selected = tmp_path / "transformation.json"
    selected.write_text("{}")
    mac_picker.return_value.stdout = str(selected)
    assert file_picker.choose_file() == str(selected)
    assert mac_picker.call_args.args[0][:2] == [file_picker.sys.executable, "-c"]


def test_tk_picker_cancellation(monkeypatch, mac_picker):
    monkeypatch.setattr(file_picker.sys, "platform", "win32")
    mac_picker.return_value.stdout = ""
    assert file_picker.choose_file() is None
