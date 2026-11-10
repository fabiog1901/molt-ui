import json

import pytest

from molt_ui.core.aggregation import LogAggregator, row_count
from molt_ui.core.jobs import OutputEvent


def feed(aggregator, **data):
    aggregator.ingest(OutputEvent(aggregator.snapshot()['totals']['log_lines'] + 1, 'stdout', json.dumps(data), data))


def test_supplied_fetch_sample_totals_and_table_attribution():
    aggregator = LogAggregator()
    for name in ('_molt_fetch_exceptions', '_molt_fetch_status'):
        feed(aggregator, level='warn', table=f'public.{name}', message='ignoring table as it is missing a definition on the source')
    counts = {'actor': 200, 'film': 1000, 'new_payment': 16044, 'payment': 16044,
              'film_actor': 5462, 'rental': 16044, 'staff': 2, 'category': 16,
              'city': 600, 'country': 109, 'customer': 599, 'language': 1, 'store': 2,
              'address': 603, 'film_category': 1000, 'film_text': 1000, 'inventory': 4581}
    for name in counts:
        feed(aggregator, level='info', source_table=f'public.{name}', target_table=f'public.{name}', message='found matching table')
    for _ in range(16):
        feed(aggregator, level='warn', message="Column 'staff_id' uses TINYINT, which is not supported in CockroachDB. Comparing as INT2, the closest equivalent.")
    feed(aggregator, level='info', type='summary', num_tables=17, message='starting fetch')
    for name, count in counts.items():
        feed(aggregator, level='info', message=f'truncating table {{public {name}}}')
        feed(aggregator, level='info', message=f'finished truncating table {{public {name}}}')
        feed(aggregator, level='info', message=f'starting fetch for table public.{name}')
        feed(aggregator, level='info', table=f'public.{name}', message='data extraction phase starting')
        feed(aggregator, level='debug', shard=1, batch=1, message='csv batch starting')
        feed(aggregator, level='debug', message=f'running copy from query: COPY public.{name} (id) FROM STDIN CSV')
        feed(aggregator, level='debug', shard=1, batch=1, message='csv batch complete')
        feed(aggregator, level='info', table=f'public.{name}', type='summary', num_rows=count, export_duration_ms=1000, message='data extraction from source complete')
    feed(aggregator, level='warn', message='sharding not supported for table public.language - single primary key with single row')
    feed(aggregator, level='info', type='summary', num_tables=17, message='fetch complete')
    snapshot = aggregator.snapshot('succeeded')
    totals = snapshot['totals']
    assert {key: totals[key] for key in ('tables', 'errors', 'warnings', 'skipped', 'exported', 'imported')} == {
        'tables': 19, 'errors': 0, 'warnings': 19, 'skipped': 2, 'exported': 63307, 'imported': 0,
    }
    assert totals['unassigned_warnings'] == 16
    rows = {row['name']: row for row in snapshot['tables']}
    assert rows['public.actor']['exported'] == 200
    assert rows['public.actor']['imported'] is None
    assert rows['public.actor']['status'] == 'exported'
    assert rows['public.language']['warnings'] == 1
    assert rows['public._molt_fetch_status']['status'] == 'skipped'
    assert rows['public.actor']['log_lines'] == 7  # Discovery, truncate pair, start, extract, COPY, summary.


def test_summaries_are_cumulative_and_repeated_records_do_not_inflate_rows():
    aggregator = LogAggregator()
    for count in (100, 200, 200, 150):
        feed(aggregator, table='public.actor', num_rows=count, message='data extraction from source complete')
    feed(aggregator, table='public.actor', num_rows=200, message='data import on target for table complete')
    feed(aggregator, table='public.actor', num_rows=200, message='data import on target for table complete')
    snapshot = aggregator.snapshot()
    assert snapshot['totals']['exported'] == 200
    assert snapshot['totals']['imported'] == 200
    assert snapshot['tables'][0]['status'] == 'imported'
    feed(aggregator, table='public.empty', num_rows=0, message='data extraction from source complete')
    assert aggregator.snapshot()['tables'][1]['exported'] == 0


def test_aliases_errors_and_global_messages_are_handled_without_worker_guessing():
    aggregator = LogAggregator()
    feed(aggregator, source_table='old.actor', target_table='new.actor', message='found matching table')
    feed(aggregator, table='new.actor', level='error', message='copy failed')
    feed(aggregator, level='fatal', message='connection lost')
    feed(aggregator, shard=2, batch=1, level='debug', message='csv batch complete')
    snapshot = aggregator.snapshot('failed')
    assert snapshot['totals']['tables'] == 1
    assert snapshot['totals']['errors'] == 2
    assert snapshot['totals']['unassigned_errors'] == 1
    assert snapshot['tables'][0]['name'] == 'old.actor'
    assert snapshot['tables'][0]['errors'] == 1
    assert snapshot['tables'][0]['log_lines'] == 2
    assert snapshot['tables'][0]['status'] == 'error'
    assert aggregator.table_logs('new.actor')['name'] == 'old.actor'


def test_detail_retention_is_globally_bounded_but_counts_cover_all_lines():
    aggregator = LogAggregator()
    for index in range(10000):
        aggregator.ingest(OutputEvent(index + 1, 'stdout', 'entry', {'table': 'public.actor', 'level': 'warn'}))
    snapshot = aggregator.snapshot()
    assert snapshot['totals']['log_lines'] == 10000
    assert snapshot['totals']['warnings'] == 10000
    assert snapshot['tables'][0]['log_lines'] == 10000
    detail = aggregator.table_logs('public.actor', limit=50)
    assert detail['total'] == 10000
    assert detail['truncated'] is True
    assert len(detail['events']) == 50
    assert detail['events'][0].sequence == 9951
    assert len(aggregator._details) == 2000
    with pytest.raises(KeyError):
        aggregator.table_logs('unknown')


@pytest.mark.parametrize('value', [True, False, -1, 1.5, '1.5', 'NaN', {}, None])
def test_invalid_row_counts_are_unknown(value):
    assert row_count(value) is None
