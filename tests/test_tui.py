import asyncio
import sys
from unittest.mock import Mock

from textual.widgets import Input, RichLog, Select, Static, TabbedContent

from molt_ui.core.models import CommandPlan
from molt_ui.core.service import MoltService
from molt_ui.molt_process import MoltProcess
from molt_ui.repo import Repo
from molt_ui.frontends.tui.app import MoltApp


def test_tui_builds_options_and_runs_shared_service(command_catalog):
    async def scenario():
        service = MoltService(MoltProcess(sys.executable), Repo(), catalog=command_catalog)
        service.preview = Mock(
            return_value=CommandPlan(
                command="fetch",
                argv=(sys.executable, "-c", 'print("help [literal]")'),
                environment={},
                options={},
                invocation="python test",
            )
        )
        service.start = Mock(wraps=service.start)
        app = MoltApp(service)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#opt-source", Input).value = "source"
            app.query_one("#opt-target", Input).value = "target"
            app.query_one("#opt-direct-copy", Select).value = "true"
            app.start_command()
            for _ in range(100):
                await pilot.pause(0.02)
                app.poll_run()
                if service.get_run(app.run.id).status != "running":
                    break
            app.poll_run()
            assert "succeeded" in str(app.query_one("#status", Static).content)
            app.query_one(TabbedContent).active = "stdout"
            await pilot.pause(0.25)
            app.poll_run()
            assert len(app.query_one("#output", RichLog).lines) > 0
            service.start.assert_called_once_with(
                "fetch",
                {"source": "source", "target": "target", "direct-copy": True},
                help_only=False,
            )
            app.query_one("#command", Select).value = "verify"
            await pilot.pause()
            assert app.query_one("#opt-rows", Select).value == ""
        service.close()

    asyncio.run(scenario())


def test_tui_shows_aggregate_counts_and_filters_table_details(command_catalog):
    from textual.widgets import DataTable

    async def scenario():
        service = MoltService(MoltProcess(sys.executable), Repo(), catalog=command_catalog)
        app = MoltApp(service)
        async with app.run_test(size=(120, 40)) as pilot:
            code = """import json
for name, rows in [('public.actor', 200), ('public.film', 1000)]:
    print(json.dumps({'level': 'info', 'table': name, 'num_rows': rows, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
"""
            service.preview = Mock(
                return_value=CommandPlan(
                    command="fetch",
                    argv=(sys.executable, "-c", code),
                    environment={},
                    options={},
                    invocation="python test",
                )
            )
            app.attach_run(service.start("fetch", {}))
            for _ in range(100):
                await pilot.pause(0.02)
                app.poll_run()
                if service.get_run(app.run.id).status != "running":
                    break
            app.poll_run()
            assert "Exported 1,200" in str(app.query_one("#summary", Static).content)
            table = app.query_one("#tables", DataTable)
            assert table.row_count == 2
            app.query_one("#table-filter", Input).value = "actor"
            await pilot.pause()
            assert table.row_count == 1
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "public.actor" in str(
                app.query_one("#table-caption", Static).content
            )
            assert app.query_one("#table-output", RichLog).display is True
            assert len(app.query_one("#table-output", RichLog).lines) > 0
        service.close()

    asyncio.run(scenario())


def test_tui_imports_the_sample_without_running_molt(command_catalog):
    from pathlib import Path
    from unittest.mock import patch
    from textual.widgets import DataTable

    async def scenario():
        sample = (
            Path(__file__).parents[1] / "src/molt_ui/webapp/static/sample-fetch.jsonl"
        )
        app = MoltApp(MoltService(MoltProcess(sys.executable), Repo(), catalog=command_catalog), log_path=str(sample))
        with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
            async with app.run_test(size=(120, 40)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert app.service.get_run(app.run.id).status == "imported"
                assert "Exported 63,307" in str(
                    app.query_one("#summary", Static).content
                )
                assert app.query_one("#tables", DataTable).row_count == 19
                app.query_one("#log-path", Input).value = "/nonexistent-molt-log.jsonl"
                app.import_log()
                await app.workers.wait_for_complete()
                assert "nonexistent-molt-log" in str(
                    app.query_one("#status", Static).content
                )
                assert (
                    app.service.get_run(app.run.id).aggregation["totals"]["exported"]
                    == 63307
                )
            spawn.assert_not_called()

    asyncio.run(scenario())
