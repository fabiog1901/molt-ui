from unittest.mock import Mock

from fastapi.testclient import TestClient

from molt_ui.frontends.api.app import create_app
from molt_ui.core import CliError, CliService, CommandResult, LogEntry


def test_api_uses_the_shared_service():
    service = Mock(spec=CliService)
    service.help.return_value = CommandResult(stdout="output", stderr="warning", returncode=1, logs=(LogEntry(stream="stderr", data={"level": "warn"}),))
    with TestClient(create_app(service)) as client:
        response = client.post("/api/cli/help")
        assert response.status_code == 200
        assert response.json() == {
            "stdout": "output", "stderr": "warning", "returncode": 1,
            "logs": [{"stream": "stderr", "data": {"level": "warn"}}],
        }
    service.help.assert_called_once_with()


def test_cli_failure_is_returned_to_the_ui():
    service = Mock(spec=CliService)
    service.help.side_effect = CliError("Executable missing")
    with TestClient(create_app(service)) as client:
        response = client.post("/api/cli/help")
        assert response.status_code == 503
        assert response.json()["detail"] == "Executable missing"


def test_frontend_assets_are_served():
    with TestClient(create_app()) as client:
        assert 'x-data="cliApp"' in client.get("/").text
        for path in ("/static/styles.css", "/static/app.js"):
            assert client.get(path).status_code == 200
        assert client.get("/api/unknown").status_code == 404


def test_job_api_runs_real_help_and_reports_validation_errors():
    import sys
    import time
    from molt_ui.core import CliRunner
    service = CliService(CliRunner(sys.executable))
    with TestClient(create_app(service)) as client:
        commands = client.get('/api/commands').json()
        assert commands[0]['id'] == 'fetch'
        assert client.post('/api/jobs', json={'command': 'invalid'}).status_code == 422
        assert client.post('/api/jobs', json={'command': 'fetch', 'options': {'direct-copy': 123}}).status_code == 422
        # Python rejects the fetch argument; still tests the real process lifecycle.
        response = client.post('/api/jobs', json={'command': 'fetch', 'help_only': True})
        assert response.status_code == 201
        job_id = response.json()['id']
        for _ in range(100):
            snapshot = client.get(f'/api/jobs/{job_id}').json()
            if snapshot['status'] != 'running':
                break
            time.sleep(.01)
        assert snapshot['status'] == 'failed'
        assert snapshot['returncode'] != 0
        assert client.get(f'/api/jobs/{job_id}?after={snapshot["cursor"]}').json()['events'] == []
        assert client.post(f'/api/jobs/{job_id}/stop').status_code == 200
        assert client.get('/api/jobs/missing').status_code == 404


def test_aggregate_snapshot_and_lazy_table_logs_are_consistent():
    import sys
    import time
    from molt_ui.core import CliRunner
    service = CliService(CliRunner(sys.executable))
    with TestClient(create_app(service)) as client:
        code = '''import json
print(json.dumps({'level': 'info', 'source_table': 'public.actor', 'target_table': 'public.actor', 'message': 'found matching table'}))
print(json.dumps({'level': 'info', 'table': 'public.actor', 'num_rows': 200, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
'''
        job = service.jobs.start(sys.executable, ['-c', code], {}, 'fetch')
        for _ in range(100):
            snapshot = client.get(f'/api/jobs/{job.id}').json()
            if snapshot['status'] != 'running':
                break
            time.sleep(.01)
        assert snapshot['aggregation']['totals']['exported'] == 200
        assert snapshot['aggregation']['totals']['warnings'] == 1
        repeated = client.get(f'/api/jobs/{job.id}?after={snapshot["cursor"]}').json()
        assert repeated['events'] == []
        assert repeated['aggregation'] == snapshot['aggregation']
        details = client.get(f'/api/jobs/{job.id}/table-logs', params={'table': 'public.actor', 'limit': 1}).json()
        assert details['total'] == 2
        assert details['truncated'] is True
        assert len(details['events']) == 1
        assert details['events'][0]['data']['num_rows'] == 200
        assert client.get(f'/api/jobs/{job.id}/table-logs', params={'table': 'unknown'}).status_code == 404
        assert client.get(f'/api/jobs/{job.id}/table-logs', params={'table': 'public.actor', 'limit': 101}).status_code == 422


def test_upload_imports_jsonl_and_preserves_a_previous_preview_on_empty_upload():
    from pathlib import Path
    with TestClient(create_app()) as client:
        sample = Path(__file__).parents[1] / 'src/molt_ui/webapp/static/sample-fetch.jsonl'
        response = client.post('/api/log-imports', content=b'\xef\xbb\xbf' + sample.read_bytes(), headers={'Content-Type': 'application/octet-stream'})
        assert response.status_code == 201
        preview = response.json()
        assert preview['status'] == 'imported'
        assert preview['returncode'] is None
        assert preview['aggregation']['totals']['exported'] == 63307
        assert preview['aggregation']['totals']['warnings'] == 19
        assert client.get('/api/jobs').json()['id'] == preview['id']
        assert client.get(f'/api/jobs/{preview["id"]}/table-logs', params={'table': 'public.actor'}).status_code == 200
        assert client.post('/api/log-imports', content=b'').status_code == 422
        assert client.get('/api/jobs').json()['id'] == preview['id']
        assert client.get('/static/sample-fetch.jsonl').status_code == 200


def test_wizard_preview_is_nonexecuting_and_history_survives_a_new_app(tmp_path):
    import sys
    import time
    from unittest.mock import patch
    from molt_ui.core import CliRunner
    from molt_ui.core.history import RunHistory
    database = str(tmp_path / 'metadata.sqlite3')
    service = CliService(CliRunner(sys.executable), RunHistory(database))
    with TestClient(create_app(service)) as client:
        with patch('molt_ui.core.jobs.subprocess.Popen') as spawn:
            response = client.post('/api/command-preview', json={
                'command': 'fetch', 'options': {'source': 'postgres://user:secret@source/db',
                    'target': 'postgres://target/db', 'direct-copy': True, 'bucket-path': 's3://bucket'},
            })
            assert response.status_code == 200
            assert response.json()['omitted'] == ['bucket-path']
            assert 'user:secret@source' in response.json()['invocation']
            assert client.get('/api/history').json() == []
            spawn.assert_not_called()
        response = client.post('/api/jobs', json={'command': 'fetch', 'help_only': True})
        assert response.status_code == 201
        job_id = response.json()['id']
        for _ in range(100):
            state = client.get(f'/api/jobs/{job_id}').json()
            if state['status'] != 'running':
                break
            time.sleep(.01)
        record_id = state['record']['id']
        assert state['record']['invocation'].endswith('fetch --help')
    restarted = CliService(CliRunner('molt'), RunHistory(database))
    with TestClient(create_app(restarted)) as client:
        records = client.get('/api/history').json()
        assert records[0]['id'] == record_id
        assert records[0]['status'] == 'failed'
        assert records[0]['returncode'] != 0
        assert records[0]['finished_at']
        assert client.get(f'/api/history/{record_id}').json() == records[0]
        assert client.get('/api/history/unknown').status_code == 404


def test_source_picker_context_is_used_by_preview_and_not_emitted_as_a_cli_flag():
    with TestClient(create_app()) as client:
        response = client.post('/api/command-preview', json={
            'command': 'fetch', 'source_kind': 'oracle', 'options': {
                'source': 'user=app password=example', 'target': 'postgres://target/db',
                'oracle-application-users': 'app', 'pglogical-replication-slot-name': 'not-for-oracle',
            },
        })
        assert response.status_code == 200
        preview = response.json()
        assert preview['omitted'] == ['pglogical-replication-slot-name']
        assert '--oracle-application-users=app' in preview['argv']
        assert not any('source_kind' in argument for argument in preview['argv'])
        assert client.post('/api/command-preview', json={
            'command': 'fetch', 'source_kind': 'oracle',
            'options': {'source': 'mysql://source/db', 'target': 'postgres://target/db'},
        }).status_code == 422
