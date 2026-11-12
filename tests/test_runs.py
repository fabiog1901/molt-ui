from io import StringIO
from pathlib import Path
import shlex
import sys
import time
from unittest.mock import patch

import pytest

from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandPlan
from molt_ui.core.runs import RunManager
from molt_ui.molt_process import MoltProcess


def python_plan(code: str, command: str = "fetch") -> CommandPlan:
    argv = (sys.executable, "-u", "-c", code)
    return CommandPlan(
        command=command,
        argv=argv,
        environment={},
        options={},
        invocation=shlex.join(argv),
    )


def wait_for(run, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = run.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.01)
    raise AssertionError("Run did not reach expected state")


def test_logs_arrive_before_completion_and_stop_reaps_process():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        code = 'import time; print(\'{"level":"info","message":"working"}\', flush=True); time.sleep(30)'
        run = manager.start(python_plan(code))
        state = wait_for(run, lambda state: state.events)
        assert state.status == "running"
        assert state.events[0].data["message"] == "working"
        with pytest.raises(MoltError, match="already running"):
            manager.start(python_plan("pass", "verify"))
        assert run.snapshot(state.cursor).events == ()
        run.stop()
        assert (
            wait_for(run, lambda state: state.status != "running").status == "stopped"
        )
        assert run.handle.wait(1)
    finally:
        manager.close()


def test_nonzero_exit_and_stderr_are_retained():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        run = manager.start(
            python_plan(
                'import sys; print("problem", file=sys.stderr); sys.exit(2)', "verify"
            )
        )
        state = wait_for(run, lambda state: state.status != "running")
        assert state.status == "failed"
        assert state.returncode == 2
        assert state.events[0].stream == "stderr"
        assert state.events[0].text == "problem"
        assert state.error == "Molt exited with code 2. problem"
    finally:
        manager.close()


@pytest.mark.parametrize("code", [
    'import sys; print("informational output", file=sys.stderr)',
    'print(\'{"level":"error","message":"recoverable error"}\')',
])
def test_successful_exit_does_not_become_failed_based_on_output(code):
    manager = RunManager(MoltProcess(sys.executable))
    try:
        run = manager.start(python_plan(code))
        state = wait_for(run, lambda state: state.status != "running")
        assert state.status == "succeeded"
        assert state.returncode == 0
        assert state.error is None
    finally:
        manager.close()


def test_signal_termination_is_reported_as_failure():
    import os
    import signal

    if os.name != "posix":
        pytest.skip("POSIX signal termination")
    manager = RunManager(MoltProcess(sys.executable))
    try:
        run = manager.start(python_plan("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"))
        state = wait_for(run, lambda state: state.status != "running")
        assert state.status == "failed"
        assert state.returncode == -signal.SIGTERM
        assert state.error == f"Molt was terminated by signal {signal.SIGTERM}."
    finally:
        manager.close()


def test_retention_is_bounded_and_reports_gaps():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        run = manager.start(python_plan("for i in range(2100): print(i)"))
        state = wait_for(run, lambda state: state.status != "running")
        assert len(state.events) == 2000
        assert state.truncated is True
        assert state.cursor == 2100
        assert state.events[0].sequence == 101
    finally:
        manager.close()


def test_aggregation_survives_raw_log_eviction():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        code = """import json
print(json.dumps({'level': 'info', 'table': 'public.actor', 'num_rows': 200, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
for i in range(3000): print('unassigned debug line')
"""
        run = manager.start(python_plan(code))
        state = wait_for(run, lambda state: state.status != "running")
        assert state.truncated is True
        assert len(state.events) == 2000
        assert state.aggregation["totals"]["exported"] == 200
        assert state.aggregation["totals"]["warnings"] == 1
        assert state.aggregation["totals"]["log_lines"] == 3002
        assert run.table_logs("public.actor").events[0].data["num_rows"] == 200
    finally:
        manager.close()


def test_import_uses_same_aggregation_without_a_process():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        path = (
            Path(__file__).parents[1] / "src/molt_ui/webapp/static/sample-fetch.jsonl"
        )
        with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
            with path.open() as source:
                run = manager.import_log(source)
            spawn.assert_not_called()
        state = run.snapshot()
        assert state.status == "imported"
        assert state.returncode is None
        assert state.aggregation["totals"]["tables"] == 19
        assert state.aggregation["totals"]["exported"] == 63307
        assert state.aggregation["totals"]["warnings"] == 19
        assert state.aggregation["totals"]["skipped"] == 2
        assert run.table_logs("public.actor").total > 0
        assert manager.latest() is run
        run.stop()
        assert run.snapshot().status == "imported"
        with pytest.raises(ValueError, match="empty"):
            manager.import_log(StringIO(""))
        assert manager.latest() is run
    finally:
        manager.close()


def test_import_preserves_bounded_history_and_an_active_run():
    manager = RunManager(MoltProcess(sys.executable))
    try:
        source = StringIO(
            '{"level":"warn","table":"public.actor","message":"example"}\n' * 3000
        )
        imported = manager.import_log(source)
        assert len(imported.snapshot().events) == 2000
        assert imported.snapshot().aggregation["totals"]["warnings"] == 3000
        run = manager.start(python_plan("import time; time.sleep(30)"))
        with pytest.raises(MoltError, match="already running"):
            manager.import_log(StringIO("example"))
        assert manager.latest() is run
    finally:
        manager.close()
