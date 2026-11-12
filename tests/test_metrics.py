import json
import math
from pathlib import Path
from threading import Event
import time
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import pytest

from molt_ui.core.metrics import MetricsEngine, counter_rate, histogram_quantile, parse_exposition
from molt_ui.core.service import MoltService
from molt_ui.frontends.api.app import create_app
from molt_ui.metrics import MetricsCollector, fetch_metrics, metrics_endpoint
from molt_ui.molt_process import MoltProcess
from molt_ui.repo import Repo


PANELS = json.loads((Path(__file__).parents[1] / 'src/molt_ui/webapp/static/metrics-dashboard.json').read_text())


def test_prometheus_labels_and_nonfinite_values():
    samples = parse_exposition(r'''# HELP molt_fetch_rows_exported Rows
molt_fetch_rows_exported{schema="public",table="a\"b\\c\nd",shard="0"} 12 1234
molt_fetch_rows_exported{table="not-a-number"} NaN
molt_fetch_rows_exported{table="infinite"} +Inf
unrelated_metric 100
''', {'molt_fetch_rows_exported'})
    assert len(samples) == 1
    (name, labels), value = next(iter(samples.items()))
    assert name == 'molt_fetch_rows_exported'
    assert dict(labels)['table'] == 'a"b\\c\nd'
    assert value == 12


def test_rates_handle_resets_and_require_two_samples_in_the_window():
    points = [(0, 100), (2, 110), (4, 5), (6, 20)]
    assert counter_rate(points, 6, 60) == 5
    assert counter_rate(points, 6, 2) is None
    assert counter_rate(points, 400, 60) is None
    assert histogram_quantile({0.1: 1, 0.5: 3, 1: 4, math.inf: 5}, 0.5) == pytest.approx(0.4)
    assert histogram_quantile({0.1: 1, 0.5: 3, 1: 4, math.inf: 5}, 0.99) == 1
    assert histogram_quantile({1: 3}, 0.5) is None
    assert histogram_quantile({1: 0, math.inf: 0}, 0.5) is None


def test_fetch_dashboard_groups_shards_and_evaluates_histogram_rates():
    engine = MetricsEngine([p for p in PANELS if p['command'] == 'fetch'])

    def exposition(multiplier):
        return '\n'.join([
            f'molt_fetch_rows_exported{{schema="public",table="actor",shard="0"}} {10 * multiplier}',
            f'molt_fetch_rows_exported{{schema="public",table="actor",shard="1"}} {20 * multiplier}',
            *[f'molt_fetch_source_query_duration_ms_bucket{{schema="public",table="actor",shard="0",le="{bound}"}} {count * (multiplier - 1)}'
              for bound, count in [('0.1', 2), ('0.5', 6), ('1', 8), ('+Inf', 10)]],
        ])

    first = engine.ingest(exposition(1), 10)
    assert first['values']['13'][0]['value'] == 30
    assert first['values']['11'] == []
    second = engine.ingest(exposition(2), 12)
    assert second['values']['13'][0]['value'] == 60
    assert second['values']['11'][0]['value'] == 15
    assert second['values']['11'][0]['labels'] == {'schema': 'public', 'table': 'actor'}
    quantiles = second['values']['24']
    assert [item['labels']['quantile'] for item in quantiles] == ['p50', 'p75', 'p90', 'p99']
    assert quantiles[0]['value'] == pytest.approx(0.4)
    assert all(item['labels']['shard'] == '0' for item in quantiles)
    assert json.loads(json.dumps(second, allow_nan=False)) == second


def test_verify_dashboard_selects_categories_and_excludes_overall_row_status():
    engine = MetricsEngine([p for p in PANELS if p['command'] == 'verify'])
    frame = engine.ingest('''molt_verify_num_tables{category="verified"} 3
molt_verify_num_tables{category="missing"} 1
molt_verify_num_tables{category="extraneous"} 2
molt_verify_rows_read{table="public.actor",side="source"} 100
molt_verify_rows_read{table="public.actor",side="target"} 100
molt_verify_row_verification_status{table="public.actor",status="match"} 99
molt_verify_row_verification_status{table="overall",status="match"} 99
''', 10)
    assert [frame['values'][key][0]['value'] for key in ('16', '17', '18')] == [3, 1, 2]
    assert frame['values']['21'][0]['value'] == 200
    assert frame['values']['22'] == [{'labels': {'status': 'match', 'table': 'public.actor'}, 'value': 99}]


@pytest.mark.parametrize('address, expected', [
    ('127.0.0.1:3030', 'http://127.0.0.1:3030/metrics'),
    ('0.0.0.0:3030', 'http://127.0.0.1:3030/metrics'),
    ('[::]:3030', 'http://[::1]:3030/metrics'),
    ('[::1]:3030', 'http://[::1]:3030/metrics'),
    ('localhost:1234', 'http://localhost:1234/metrics'),
])
def test_metrics_endpoint_uses_the_configured_listener(address, expected):
    assert metrics_endpoint(address) == expected


@pytest.mark.parametrize('address', ['localhost', 'host:0', 'host:65536', 'user:password@host:3030', 'host:3030/other', 'http://host:3030'])
def test_metrics_endpoint_rejects_non_listener_addresses(address):
    with pytest.raises(ValueError):
        metrics_endpoint(address)


def test_metrics_retention_incremental_reads_restart_and_deletion(tmp_path, monkeypatch):
    import molt_ui.repo.repo as repo_module

    monkeypatch.setattr(repo_module, 'SAMPLE_LIMIT', 3)
    database = str(tmp_path / 'metrics.sqlite3')
    repo = Repo(database)
    record = repo.create_run('fetch', origin='command')
    for index in range(6):
        repo.save_metrics(record.id, {'status': 'collecting'}, {'timestamp': index + 1, 'values': {}})
    repo.close()
    repo = Repo(database)
    try:
        state, frames = repo.get_metrics(record.id)
        assert state['status'] == 'collecting'
        assert [frame['timestamp'] for frame in frames] == [4, 5, 6]
        assert [frame['timestamp'] for frame in repo.get_metrics(record.id, 4)[1]] == [5, 6]
        repo.delete_run(record.id)
        assert repo.get_metrics(record.id) == (None, [])
    finally:
        repo.close()


def test_collector_retries_failure_with_a_gap_and_closes_before_persistence_ends():
    saved, sampled = [], Event()
    calls = 0

    def fetch(endpoint):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError('endpoint is starting')
        return 'molt_fetch_num_tables 4\n'

    def save(state, frame):
        saved.append((state, frame))
        if frame and frame['values'].get('1'):
            sampled.set()

    collector = MetricsCollector('http://localhost:3030/metrics',
        [p for p in PANELS if p['command'] == 'fetch'], save, interval=.01, fetch=fetch)
    collector.start()
    try:
        assert sampled.wait(2)
    finally:
        collector.close()
    assert saved[0][0]['status'] == 'unreachable'
    assert saved[0][1]['values'] == {}
    assert saved[-1][0]['status'] == 'complete'
    assert saved[-1][0]['error'] is None
    assert any(frame and frame['values'].get('1') for _, frame in saved)


@pytest.mark.parametrize('returncode, status', [(0, 'succeeded'), (2, 'failed')])
def test_service_collects_in_background_and_api_history_survives_restart(command_catalog, tmp_path, returncode, status):
    database = str(tmp_path / 'service-metrics.sqlite3')
    process = MoltProcess('molt')
    callbacks = {}

    def start(arguments, **kwargs):
        callbacks.update(kwargs)
        handle = Mock()
        handle.close.side_effect = lambda: kwargs['on_exit'](returncode, False)
        return handle

    service = MoltService(process, Repo(database), catalog=command_catalog)
    with patch.object(process, 'start', side_effect=start), patch(
        'molt_ui.metrics.fetch_metrics', return_value='molt_fetch_num_tables 4\n'
    ):
        run = service.start('fetch', {'metrics-listen-addr': '0.0.0.0:4321'})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            data = service.get_run_metrics(run.id)
            if data['frames']:
                break
            time.sleep(.01)
        assert data['frames'][0]['values']['1'][0]['value'] == 4
        assert data['state']['endpoint'] == 'http://127.0.0.1:4321/metrics'
        assert service.get_run_metrics(run.id, data['frames'][-1]['timestamp'])['frames'] == []
        assert service.get_run(run.id).status == 'running'
        service.close()
    restarted = MoltService(MoltProcess('molt'), Repo(database))
    with TestClient(create_app(restarted)) as client:
        response = client.get(f'/api/history/{run.record.id}/metrics')
        assert response.status_code == 200
        saved = response.json()
        assert saved['state']['status'] == 'complete'
        assert client.get(f'/api/history/{run.record.id}').json()['status'] == status
        assert saved['frames'][0]['values']['1'][0]['value'] == 4
        assert client.get('/api/history/missing/metrics').status_code == 404
        assert client.get(f'/api/history/{run.record.id}/metrics?after=inf').status_code == 422
        assert client.get('/static/vendor/uPlot.iife.min.js').status_code == 200
        assert client.delete(f'/api/history/{run.record.id}').status_code == 200
        assert client.get(f'/api/history/{run.record.id}/metrics').status_code == 404


def test_http_collection_reads_prometheus_text_without_a_proxy_or_redirect():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/metrics')
                self.end_headers()
                return
            assert self.path == '/metrics'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'molt_fetch_num_tables 3\n')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        assert fetch_metrics(url + '/metrics') == 'molt_fetch_num_tables 3\n'
        with pytest.raises(OSError):
            fetch_metrics(url + '/redirect')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
