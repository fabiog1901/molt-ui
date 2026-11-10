import sys
from unittest.mock import Mock

import pytest

from molt_ui.core import CliError, CliRunner, CliService, create_service


def test_runner_preserves_streams_exit_code_and_structured_logs():
    code = '''import sys
print('{"level":"warn","table":"public.example","message":"ignored"}')
print("plain error", file=sys.stderr)
sys.exit(3)
'''
    result = CliRunner(sys.executable).run(["-c", code])
    assert result.returncode == 3
    assert result.stderr == "plain error\n"
    assert result.logs[0].stream == "stdout"
    assert result.logs[0].data["table"] == "public.example"


def test_arguments_are_passed_literally_without_a_shell():
    argument = "hello; $(echo unexpected)"
    result = CliRunner(sys.executable).run(["-c", "import sys; print(sys.argv[1])", argument])
    assert result.stdout.strip() == argument


def test_runner_handles_missing_executable():
    with pytest.raises(CliError, match="Could not start CLI"):
        CliRunner("/nonexistent-molt-test-executable").run([])


def test_runner_times_out():
    with pytest.raises(CliError, match="timed out"):
        CliRunner(sys.executable, timeout=0.05).run(["-c", "import time; time.sleep(5)"])


def test_log_parser_accepts_mixed_output_on_both_streams():
    code = '''import sys
print("not JSON")
print("[]")
print("{broken")
print('{"level":"info","message":"checking database details"}')
print('{"level":"debug","flush_size":1048576}', file=sys.stderr)
'''
    result = CliRunner(sys.executable).run(["-c", code])
    assert len(result.logs) == 2
    assert result.logs[1].stream == "stderr"
    assert result.logs[1].data["flush_size"] == 1048576


def test_help_is_a_named_operation_and_executable_is_configurable(monkeypatch, tmp_path):
    from molt_ui.core import cli

    runner = Mock()
    CliService(runner).help()
    runner.run.assert_called_once_with(["--help"])
    local_binary = tmp_path / "molt" / "molt"
    monkeypatch.setattr(cli, "LOCAL_EXECUTABLE", local_binary)
    monkeypatch.delenv("MOLT_EXECUTABLE", raising=False)
    assert create_service().runner.executable == "molt"
    local_binary.parent.mkdir()
    local_binary.touch()
    monkeypatch.chdir(tmp_path.parent)
    assert create_service().runner.executable == str(local_binary)
    monkeypatch.setenv("MOLT_EXECUTABLE", "/custom/molt")
    assert create_service().runner.executable == "/custom/molt"
