import sys
import time

import pytest

from molt_ui.core import CliError
from molt_ui.core.jobs import JobManager


def wait_for(job, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = job.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(.01)
    raise AssertionError('Job did not reach expected state')


def test_logs_are_available_before_process_finishes_and_stop_reaps_process():
    manager = JobManager()
    try:
        code = 'import time; print(\'{"level":"info","message":"working"}\', flush=True); time.sleep(30)'
        job = manager.start(sys.executable, ['-u', '-c', code], {}, 'fetch')
        snapshot = wait_for(job, lambda state: state['events'])
        assert snapshot['status'] == 'running'
        assert snapshot['events'][0].data['message'] == 'working'
        with pytest.raises(CliError, match='already running'):
            manager.start(sys.executable, ['-c', 'pass'], {}, 'verify')
        assert job.snapshot(snapshot['cursor'])['events'] == []
        job.stop()
        final = wait_for(job, lambda state: state['status'] != 'running')
        assert final['status'] == 'stopped'
        assert job.process.poll() is not None
    finally:
        manager.close()


def test_nonzero_exit_and_stderr_are_retained():
    manager = JobManager()
    try:
        job = manager.start(sys.executable, ['-c', 'import sys; print("problem", file=sys.stderr); sys.exit(2)'], {}, 'verify')
        snapshot = wait_for(job, lambda state: state['status'] != 'running')
        assert snapshot['status'] == 'failed'
        assert snapshot['returncode'] == 2
        assert snapshot['events'][0].stream == 'stderr'
        assert snapshot['events'][0].text == 'problem'
    finally:
        manager.close()


def test_log_retention_is_bounded_and_reports_gaps():
    manager = JobManager()
    try:
        job = manager.start(sys.executable, ['-c', 'for i in range(2100): print(i)'], {}, 'fetch')
        snapshot = wait_for(job, lambda state: state['status'] != 'running')
        assert len(snapshot['events']) == 2000
        assert snapshot['truncated'] is True
        assert snapshot['cursor'] == 2100
        assert snapshot['events'][0].sequence == 101
    finally:
        manager.close()


def test_aggregation_survives_raw_log_eviction():
    manager = JobManager()
    try:
        code = '''import json
print(json.dumps({'level': 'info', 'table': 'public.actor', 'num_rows': 200, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
for i in range(3000): print('unassigned debug line')
'''
        job = manager.start(sys.executable, ['-c', code], {}, 'fetch')
        snapshot = wait_for(job, lambda state: state['status'] != 'running')
        assert snapshot['truncated'] is True
        assert len(snapshot['events']) == 2000
        assert snapshot['aggregation']['totals']['exported'] == 200
        assert snapshot['aggregation']['totals']['warnings'] == 1
        assert snapshot['aggregation']['totals']['log_lines'] == 3002
        assert job.table_logs('public.actor')['events'][0].data['num_rows'] == 200
    finally:
        manager.close()


def test_imported_logs_use_the_same_aggregator_without_spawning_a_process():
    from io import StringIO
    from pathlib import Path
    from unittest.mock import patch
    manager = JobManager()
    try:
        path = Path(__file__).parents[1] / 'src/molt_ui/webapp/static/sample-fetch.jsonl'
        with patch('molt_ui.core.jobs.subprocess.Popen') as spawn:
            with path.open() as source:
                job = manager.import_log(source)
            spawn.assert_not_called()
        state = job.snapshot()
        assert state['status'] == 'imported'
        assert state['returncode'] is None
        assert state['aggregation']['totals']['tables'] == 19
        assert state['aggregation']['totals']['exported'] == 63307
        assert state['aggregation']['totals']['warnings'] == 19
        assert state['aggregation']['totals']['skipped'] == 2
        assert job.table_logs('public.actor')['total'] > 0
        assert manager.latest() is job
        job.stop()
        assert job.snapshot()['status'] == 'imported'
        with pytest.raises(ValueError, match='empty'):
            manager.import_log(StringIO(''))
        assert manager.latest() is job
    finally:
        manager.close()


def test_import_keeps_bounded_history_and_preserves_an_active_run():
    from io import StringIO
    manager = JobManager()
    try:
        source = StringIO('{"level":"warn","table":"public.actor","message":"example"}\n' * 3000)
        imported = manager.import_log(source)
        snapshot = imported.snapshot()
        assert len(snapshot['events']) == 2000
        assert snapshot['aggregation']['totals']['warnings'] == 3000
        job = manager.start(sys.executable, ['-c', 'import time; time.sleep(30)'], {}, 'fetch')
        with pytest.raises(CliError, match='Stop the active'):
            manager.import_log(StringIO('example'))
        assert manager.latest() is job
    finally:
        manager.close()
