import asyncio
import sys
from unittest.mock import Mock

from textual.widgets import Input, RichLog, Select, Static, TabbedContent

from molt_ui.core import CliRunner, CliService
from molt_ui.tui.app import MoltApp


def test_tui_builds_options_and_runs_shared_service():
    async def scenario():
        service = CliService(CliRunner(sys.executable))
        original_start = service.jobs.start
        def start(command, options, *, help_only=False):
            return original_start(sys.executable, ['-c', 'print("help [literal]")'], {}, command)
        service.start = Mock(side_effect=start)
        app = MoltApp(service)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one('#opt-source', Input).value = 'source'
            app.query_one('#opt-target', Input).value = 'target'
            app.query_one('#opt-direct-copy', Select).value = 'true'
            app.start_command()
            for _ in range(100):
                await pilot.pause(.02)
                app.poll_job()
                if app.job.snapshot()['status'] != 'running':
                    break
            app.poll_job()
            assert 'succeeded' in str(app.query_one('#status', Static).content)
            app.query_one(TabbedContent).active = "stdout"
            await pilot.pause(.25)
            app.poll_job()
            assert len(app.query_one("#output", RichLog).lines) > 0
            service.start.assert_called_once_with('fetch', {'source': 'source', 'target': 'target', 'direct-copy': True}, help_only=False)
            app.query_one('#command', Select).value = 'verify'
            await pilot.pause()
            assert app.query_one('#opt-rows', Select).value == ''
        service.close()
    asyncio.run(scenario())


def test_tui_shows_aggregate_counts_and_filters_table_details():
    from textual.widgets import DataTable

    async def scenario():
        service = CliService(CliRunner(sys.executable))
        app = MoltApp(service)
        async with app.run_test(size=(120, 40)) as pilot:
            code = '''import json
for name, rows in [('public.actor', 200), ('public.film', 1000)]:
    print(json.dumps({'level': 'info', 'table': name, 'num_rows': rows, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
'''
            app.job = service.jobs.start(sys.executable, ['-c', code], {}, 'fetch')
            for _ in range(100):
                await pilot.pause(.02)
                app.poll_job()
                if app.job.snapshot()['status'] != 'running':
                    break
            app.poll_job()
            assert 'Exported 1,200' in str(app.query_one('#summary', Static).content)
            table = app.query_one('#tables', DataTable)
            assert table.row_count == 2
            app.query_one('#table-filter', Input).value = 'actor'
            await pilot.pause()
            assert table.row_count == 1
            table.focus()
            await pilot.press('enter')
            await pilot.pause()
            assert 'public.actor' in str(app.query_one('#table-caption', Static).content)
            assert app.query_one('#table-output', RichLog).display is True
            assert len(app.query_one('#table-output', RichLog).lines) > 0
        service.close()
    asyncio.run(scenario())


def test_tui_imports_the_sample_without_running_molt():
    from pathlib import Path
    from unittest.mock import patch
    from textual.widgets import DataTable

    async def scenario():
        sample = Path(__file__).parents[1] / 'src/molt_ui/web/static/sample-fetch.jsonl'
        app = MoltApp(log_path=str(sample))
        with patch('molt_ui.core.jobs.subprocess.Popen') as spawn:
            async with app.run_test(size=(120, 40)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert app.job.snapshot()['status'] == 'imported'
                assert 'Exported 63,307' in str(app.query_one('#summary', Static).content)
                assert app.query_one('#tables', DataTable).row_count == 19
                app.query_one('#log-path', Input).value = '/nonexistent-molt-log.jsonl'
                app.import_log()
                await app.workers.wait_for_complete()
                assert 'nonexistent-molt-log' in str(app.query_one('#status', Static).content)
                assert app.job.snapshot()['aggregation']['totals']['exported'] == 63307
            spawn.assert_not_called()
    asyncio.run(scenario())
