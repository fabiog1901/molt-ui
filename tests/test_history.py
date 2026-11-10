from pathlib import Path
import shlex
import sys
import time
from unittest.mock import patch

import pytest

from molt_ui.core import CliError, CliRunner, CliService
from molt_ui.core.history import RunHistory


def wait_for(job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = job.snapshot()
        if state['status'] != 'running':
            return state
        time.sleep(.01)
    raise AssertionError('Job did not finish')


def test_exact_invocation_including_credentials_roundtrips_sqlite(tmp_path):
    path = str(tmp_path / 'runs.sqlite3')
    store = RunHistory(path)
    service = CliService(CliRunner('/path with spaces/molt'), store)
    source = "postgres://user:p@ss$word@source/db?sslmode=require"
    options = {'source': source, 'target': 'postgres://target/db', 'direct-copy': True, 'table-filter': "public.weird table; $(echo nope)"}
    plan = service.preview('fetch', options)
    assert source in plan['invocation']
    assert shlex.split(plan['invocation'])[0] == 'MOLT_SOURCE=' + source
    assert not any(arg.startswith('--log-file=') for arg in plan['argv'])
    with patch('molt_ui.core.jobs.subprocess.Popen', side_effect=FileNotFoundError('missing binary')):
        with pytest.raises(CliError):
            service.start('fetch', options)
    fresh = RunHistory(path)
    records = fresh.list()
    assert len(records) == 1
    saved = records[0]
    assert saved['invocation'] == plan['invocation']
    assert saved['environment']['MOLT_SOURCE'] == source
    assert saved['argv'] == plan['argv']
    assert saved['options'] == options
    assert saved['status'] == 'launch_failed'
    assert saved['finished_at'] is not None
    assert saved['error']
    assert fresh.get(saved['id']) == saved
    if sys.platform != 'win32':
        assert Path(path).stat().st_mode & 0o777 == 0o600
    service.close()


def test_record_completes_durably_even_without_any_polling(tmp_path):
    path = str(tmp_path / 'runs.sqlite3')
    store = RunHistory(path)
    service = CliService(CliRunner(sys.executable), store)
    # Use Python's help command as a harmless process, with a named operation plan.
    plan = dict(argv=[sys.executable, '--help'], environment={}, options={}, invocation=shlex.join([sys.executable, '--help']))
    with patch.object(service, 'preview', return_value=plan):
        job = service.start('fetch', {}, help_only=True)
    state = wait_for(job)
    assert state['status'] == 'succeeded'
    record = RunHistory(path).get(state['record']['id'])
    assert record['status'] == 'succeeded'
    assert record['origin'] == 'help'
    assert record['returncode'] == 0
    assert record['summary']['log_lines'] > 0
    assert record['finished_at']
    assert record['invocation'] == plan['invocation']
    service.close()


def test_preview_prunes_inapplicable_flags_and_does_not_create_a_record():
    service = CliService(CliRunner('molt'))
    source = 'postgres://source/db'
    with patch('molt_ui.core.jobs.subprocess.Popen') as spawn:
        plan = service.preview('fetch', {'source': source, 'target': 'postgres://target/db', 'direct-copy': True,
                                        'bucket-path': 's3://bucket', 'assume-role': 'role', 'oracle-application-users': 'user'})
        spawn.assert_not_called()
    assert set(plan['omitted']) == {'bucket-path', 'assume-role', 'oracle-application-users'}
    assert 'bucket-path' not in plan['options']
    assert service.history.list() == []
    service.close()


def test_import_records_have_no_fabricated_command(tmp_path):
    from io import StringIO
    path = str(tmp_path / 'runs.sqlite3')
    service = CliService(CliRunner('molt'), RunHistory(path))
    job = service.import_log(StringIO('{"table":"public.actor","num_rows":200,"message":"data extraction from source complete"}\n'))
    record = RunHistory(path).get(job.snapshot()['record']['id'])
    assert record['status'] == 'imported'
    assert record['invocation'] is None
    assert record['origin'] == 'import'
    assert record['returncode'] is None
    assert record['summary']['exported'] == 200
    service.close()
