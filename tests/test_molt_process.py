import sys
from unittest.mock import Mock

import pytest

from molt_ui.core.errors import MoltError
from molt_ui.molt_process import MoltProcess


def test_runner_preserves_streams_exit_code_and_structured_logs():
    code = """import sys
print('{"level":"warn","table":"public.example","message":"ignored"}')
print("plain error", file=sys.stderr)
sys.exit(3)
"""
    result = MoltProcess(sys.executable).run(["-c", code])
    assert result.returncode == 3
    assert result.stderr == "plain error\n"
    assert result.logs[0].stream == "stdout"
    assert result.logs[0].data["table"] == "public.example"


def test_arguments_are_passed_literally_without_a_shell():
    argument = "hello; $(echo unexpected)"
    result = MoltProcess(sys.executable).run(
        ["-c", "import sys; print(sys.argv[1])", argument]
    )
    assert result.stdout.strip() == argument


def test_runner_handles_missing_executable():
    with pytest.raises(MoltError, match="Could not start CLI"):
        MoltProcess("/nonexistent-molt-test-executable").run([])


def test_runner_times_out():
    with pytest.raises(MoltError, match="timed out"):
        MoltProcess(sys.executable, timeout=0.05).run(
            ["-c", "import time; time.sleep(5)"]
        )


def test_log_parser_accepts_mixed_output_on_both_streams():
    code = """import sys
print("not JSON")
print("[]")
print("{broken")
print('{"level":"info","message":"checking database details"}')
print('{"level":"debug","flush_size":1048576}', file=sys.stderr)
"""
    result = MoltProcess(sys.executable).run(["-c", code])
    assert len(result.logs) == 2
    assert result.logs[1].stream == "stderr"
    assert result.logs[1].data["flush_size"] == 1048576


def test_stop_escalates_when_the_process_ignores_termination():
    import os
    from threading import Event

    if os.name != "posix":
        pytest.skip("POSIX signal handling")
    ready = Event()
    results = []
    process = MoltProcess(sys.executable)
    code = 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("ready",flush=True); time.sleep(30)'
    handle = process.start(
        ["-u", "-c", code],
        environment={},
        on_output=lambda text, stream: ready.set() if text == "ready" else None,
        on_exit=lambda code, stopped: results.append((code, stopped)),
    )
    try:
        assert ready.wait(3)
        handle.stop()
        assert handle.wait(5)
        assert results[0][0] != 0
        assert results[0][1] is True
    finally:
        handle.close()
