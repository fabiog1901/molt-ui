import sys
from unittest.mock import Mock, patch
from urllib.parse import quote

from fastapi.testclient import TestClient

from molt_ui.core.models import CommandPlan
from molt_ui.core.service import MoltService
from molt_ui.frontends.api.app import create_app
from molt_ui.molt_process import MoltProcess
from molt_ui.repo import Repo


LOG_NAME = 'verify-2026-11-12T17.50.58Z.log'
LOG_ID = '2026-11-12T17.50.58Z'


def test_log_upload_uses_filename_timestamp_and_rejects_repeat_imports():
    service = MoltService(MoltProcess('/unused'), Repo())
    with TestClient(create_app(service)) as client:
        response = client.post('/api/log-imports', content='original output\n',
                               headers={'X-Log-Filename': quote(LOG_NAME)})
        assert response.status_code == 201
        imported = response.json()
        assert imported['id'] == imported['record']['id'] == LOG_ID
        assert client.get(f'/api/jobs/{quote(LOG_ID, safe="")}').status_code == 200
        duplicate = client.post('/api/log-imports', content='replacement output\n',
                                headers={'X-Log-Filename': quote(LOG_NAME)})
        assert duplicate.status_code == 409
        assert 'Duplicate timestamps' in duplicate.json()['detail']
        saved = client.get(f'/api/history/{quote(LOG_ID, safe="")}/output').json()
        assert saved['events'][0]['text'] == 'original output'
        assert service.latest_run().id == LOG_ID


def test_open_log_file_uses_its_name_without_an_upload_header(tmp_path):
    path = tmp_path / LOG_NAME
    path.write_text('saved log\n')
    service = MoltService(MoltProcess('/unused'), Repo())
    try:
        with path.open() as source:
            imported = service.import_log(source)
        assert imported.id == imported.record.id == LOG_ID
        assert service.get_history_output(LOG_ID).events[0].text == 'saved log'
    finally:
        service.close()


def test_duplicate_explicit_log_timestamp_is_rejected_before_process_launch(command_catalog):
    repo = Repo()
    original = repo.create_run('verify', origin='command', log_name=LOG_NAME)
    original = repo.update_run(original.id, status='succeeded', returncode=0)
    service = MoltService(MoltProcess('molt'), repo, catalog=command_catalog)
    with TestClient(create_app(service)) as client:
        with patch('molt_ui.molt_process.subprocess.Popen') as spawn:
            response = client.post('/api/jobs', json={'command': 'verify', 'options': {'log-file': LOG_NAME}})
            assert response.status_code == 409
            spawn.assert_not_called()
        assert service.list_history() == [original]


def test_completed_molt_log_rekeys_history_but_keeps_live_polling_id_stable(tmp_path):
    path = tmp_path / LOG_NAME
    path.write_text('log output\n')
    repo = Repo()
    process = MoltProcess(sys.executable)
    service = MoltService(process, repo)
    plan = CommandPlan(command='verify', argv=(sys.executable, '-c', 'pass'),
                       environment={}, options={}, invocation='test')

    def start(arguments, **callbacks):
        record = service.list_history()[0]
        repo.save_metrics(record.id, {'status': 'complete'}, {'timestamp': 1, 'values': {}})
        callbacks['on_output']('captured output', 'stdout')
        callbacks['on_log_file'](str(path))
        callbacks['on_exit'](0, False)
        return Mock()

    try:
        with patch.object(service, 'preview', return_value=plan), patch.object(process, 'start', side_effect=start):
            run = service.start('verify', {})
        assert run.id != LOG_ID
        assert run.record.id == LOG_ID
        assert run.history_error is None
        assert service.get_run(run.id).status == 'succeeded'
        assert service.get_history_output(LOG_ID).events[0].text == 'log output'
        assert service.get_history_metrics(LOG_ID)['frames'][0]['timestamp'] == 1
    finally:
        service.close()


def test_late_duplicate_log_timestamp_preserves_both_attempts_and_terminal_status(tmp_path):
    path = tmp_path / LOG_NAME
    path.write_text('new log output\n')
    repo = Repo()
    original = repo.create_run('verify', origin='command', log_name=LOG_NAME)
    original = repo.update_run(original.id, status='failed', returncode=2, error='original diagnostic')
    process = MoltProcess(sys.executable)
    service = MoltService(process, repo)
    plan = CommandPlan(command='verify', argv=(sys.executable, '-c', 'pass'),
                       environment={}, options={}, invocation='test')

    def start(arguments, **callbacks):
        callbacks['on_output']('new attempt output', 'stdout')
        callbacks['on_log_file'](str(path))
        callbacks['on_exit'](0, False)
        return Mock()

    try:
        with patch.object(service, 'preview', return_value=plan), patch.object(process, 'start', side_effect=start):
            run = service.start('verify', {})
        assert run.status == 'succeeded'
        assert 'Duplicate timestamps' in run.history_error
        assert service.get_history_record(LOG_ID) == original
        attempted = service.get_history_record(run.id)
        assert attempted.status == 'succeeded'
        assert attempted.returncode == 0
        assert 'Duplicate timestamps' in attempted.error
        assert service.get_history_output(run.id).events[0].text == 'new attempt output'
        assert len(service.list_history()) == 2
    finally:
        service.close()
