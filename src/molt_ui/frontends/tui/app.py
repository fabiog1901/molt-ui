from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, Label, RichLog, Select, Static, TabbedContent, TabPane

from molt_ui.core import CliError, CliService, create_service
from molt_ui.frontends.models import CommandDefinition


class MoltApp(App):
    TITLE = "Molt UI"
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+r", "run_command", "Run")]
    CSS = """
    #layout { height: 1fr; }
    #form { width: 1fr; padding: 1 2; }
    #console { width: 1fr; padding: 1; }
    #fields { height: auto; }
    .field { height: auto; margin-bottom: 1; }
    .field Label { height: auto; }
    #actions { height: auto; padding: 1; }
    #actions Button { margin-right: 1; min-width: 10; }
    #status { height: auto; margin-bottom: 1; }
    #output { height: 1fr; border: round $primary; }
    #summary { height: auto; margin-bottom: 1; }
    #table-filter { height: 3; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; }
    #tables { height: 1fr; }
    #table-caption { height: auto; }
    #table-output { height: 5; border: round $secondary; display: none; }
    #notice { height: auto; margin: 1 0; color: $text-muted; }
    """

    def __init__(self, service: CliService | None = None, *, log_path: str = "") -> None:
        super().__init__()
        self.service = service if service is not None else create_service()
        self.catalog = [CommandDefinition.model_validate(item) for item in self.service.commands()]
        self.job = None
        self.cursor = 0
        self.output_cursor = 0
        self.loading_fields = False
        self.aggregation = {"totals": {}, "tables": []}
        self.selected_table: str | None = None
        self.table_log_count = -1
        self.table_signature = None
        self.table_rows = {}
        self.initial_log_path = log_path
        self.importing = False
        self.last_error = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            with VerticalScroll(id="form"):
                yield Label("Preview a saved log")
                yield Input(value=self.initial_log_path, placeholder="Path to .jsonl or .log file", id="log-path")
                yield Button("Import log", id="import-log")
                yield Label("Command")
                yield Select([(item.label, item.id) for item in self.catalog], value="fetch", allow_blank=False, id="command")
                yield Static("Run executes against your configured databases. Stop ends the process; it does not undo completed work.", id="notice")
                yield Checkbox("Show advanced options", id="advanced")
                yield Vertical(id="fields")
            with Vertical(id="console"):
                yield Static("Ready", id="status", markup=False)
                yield Static("Tables 0 · Errors 0 · Warnings 0 · Skipped 0\nExported 0 · Imported 0", id="summary", markup=False)
                with TabbedContent():
                    with TabPane("Tables", id="progress"):
                        yield Input(placeholder="Filter table name…", id="table-filter")
                        yield DataTable(id="tables", cursor_type="row")
                        yield Static("Select a table for recent logs", id="table-caption", markup=False)
                        yield RichLog(id="table-output", markup=False, highlight=False, wrap=True, max_lines=100)
                    with TabPane("Output", id="stdout"):
                        yield RichLog(id="output", markup=False, highlight=False, wrap=True, max_lines=2000)
        with Horizontal(id="actions"):
            yield Button("Run", id="run", variant="primary")
            yield Button("Help", id="help")
            yield Button("Stop", id="stop", variant="error", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#tables", DataTable).add_columns("Table", "Exported", "Imported", "Errors", "Warnings", "Logs", "Status")
        await self.render_fields()
        self.set_interval(0.2, self.poll_job)
        if self.initial_log_path:
            self.import_log()

    def definition(self) -> CommandDefinition:
        command = self.query_one("#command", Select).value
        return next(item for item in self.catalog if item.id == command)

    async def render_fields(self) -> None:
        self.loading_fields = True
        try:
            container = self.query_one("#fields", Vertical)
            await container.remove_children()
            for option in self.definition().options:
                name = option.name
                field = Vertical(classes="field advanced" if option.advanced else "field")
                await container.mount(field)
                await field.mount(Label(f"--{name}"))
                if option.kind == "bool":
                    widget = Select([("CLI default", ""), ("Yes", "true"), ("No", "false")], value="", allow_blank=False, id=f"opt-{name}")
                else:
                    widget = Input(password=option.secret, id=f"opt-{name}", placeholder="CLI default")
                widget.tooltip = option.description
                await field.mount(widget)
            self.toggle_advanced()
        finally:
            self.loading_fields = False

    @on(Select.Changed, "#command")
    async def command_changed(self) -> None:
        if self.is_mounted and not self.loading_fields:
            await self.render_fields()

    @on(Checkbox.Changed, "#advanced")
    def toggle_advanced(self) -> None:
        visible = self.query_one("#advanced", Checkbox).value
        for field in self.query(".advanced"):
            field.display = visible

    def options(self) -> dict[str, str | bool]:
        values = {}
        for option in self.definition().options:
            widget = self.query_one(f"#opt-{option.name}")
            value = widget.value
            if value != "":
                values[option.name] = value == "true" if option.kind == "bool" else value
        return values

    @on(Button.Pressed, "#run")
    def action_run_command(self) -> None:
        self.start_command()

    @on(Button.Pressed, "#help")
    def show_help(self) -> None:
        self.start_command(help_only=True)

    def start_command(self, *, help_only: bool = False) -> None:
        self.launch(help_only)

    def launch(self, help_only: bool) -> None:
        if self.importing:
            return
        if self.job and self.job.snapshot()["status"] == "running":
            return
        try:
            self.job = self.service.start(self.definition().id, self.options(), help_only=help_only)
        except (ValueError, CliError) as exc:
            self.show_error(str(exc))
            return
        self.attach_job(self.job)

    def attach_job(self, job) -> None:
        self.job = job
        self.last_error = None
        self.cursor = 0
        self.output_cursor = 0
        self.selected_table = None
        self.table_log_count = -1
        self.table_signature = None
        self.table_rows = {}
        self.query_one("#output", RichLog).clear()
        self.query_one("#table-output", RichLog).clear()
        self.query_one("#table-output", RichLog).display = False
        self.query_one("#table-caption", Static).update("Select a table for recent logs")
        self.poll_job()

    @on(Button.Pressed, "#import-log")
    @on(Input.Submitted, "#log-path")
    @work(exclusive=True, group="import-log")
    async def import_log(self) -> None:
        import asyncio
        from pathlib import Path

        path = self.query_one("#log-path", Input).value.strip()
        if not path:
            self.show_error("Enter a log file path.")
            return
        self.importing = True
        self.set_running(True)
        self.query_one("#status", Static).update("Importing log…")
        loaded = False

        def read_log():
            with Path(path).expanduser().open(encoding="utf-8-sig", errors="replace") as source:
                return self.service.import_log(source)

        try:
            self.attach_job(await asyncio.to_thread(read_log))
            loaded = True
        except (OSError, ValueError, CliError) as exc:
            self.show_error(str(exc))
        finally:
            self.importing = False
            self.set_running(self.job is not None and self.job.snapshot()["status"] == "running")
        if loaded:
            self.poll_job()

    def set_running(self, running: bool) -> None:
        for selector in ("#run", "#help", "#command", "#fields", "#import-log", "#log-path"):
            self.query_one(selector).disabled = running
        self.query_one("#stop", Button).disabled = not running or self.importing

    def show_error(self, message: str) -> None:
        self.last_error = message
        self.query_one("#status", Static).update(message)

    def poll_job(self) -> None:
        if not self.is_running or self.job is None or self.importing:
            return
        output = self.query_one("#output", RichLog)
        show_output = self.query_one(TabbedContent).active == "stdout" and output.size.width > 0
        snapshot = self.job.snapshot(self.output_cursor if show_output else self.cursor)
        self.aggregation = snapshot["aggregation"]
        totals = self.aggregation["totals"]
        self.query_one("#summary", Static).update(
            f"Tables {totals['tables']:,} · Errors {totals['errors']:,} · Warnings {totals['warnings']:,} · Skipped {totals['skipped']:,}\n"
            f"Exported {totals['exported']:,} · Imported {totals['imported']:,} · Global warnings {totals['unassigned_warnings']:,}"
        )
        self.update_tables()
        self.update_table_logs()
        if show_output:
            if snapshot["truncated"]:
                output.write("Earlier output was discarded from the bounded log buffer.")
            for event in snapshot["events"]:
                output.write(f"[{event.stream}] {event.text}")
            self.output_cursor = snapshot["cursor"]
        self.cursor = snapshot["cursor"]
        status = snapshot["status"] + (f" · exit {snapshot['returncode']}" if snapshot["returncode"] is not None else "")
        self.query_one("#status", Static).update(self.last_error or snapshot.get('history_error') or status)
        self.set_running(snapshot["status"] == "running")

    @on(TabbedContent.TabActivated)
    def output_tab_changed(self) -> None:
        # Hidden RichLog widgets otherwise accumulate deferred renders before
        # their first layout. Read the bounded core buffer when the tab opens.
        self.call_after_refresh(self.poll_job)

    @on(Input.Changed, "#table-filter")
    def filter_tables(self) -> None:
        self.table_signature = None
        self.update_tables()

    def update_tables(self) -> None:
        term = self.query_one("#table-filter", Input).value.casefold()
        rows = [row for row in self.aggregation["tables"] if term in f"{row['name']} {row['target'] or ''}".casefold()]
        # The terminal table is virtualized; no log widgets are created per row.
        signature = [(row["name"], row["exported"], row["imported"], row["errors"], row["warnings"], row["log_lines"], row["status"]) for row in rows]
        if signature == self.table_signature:
            return
        self.table_signature = signature
        table = self.query_one("#tables", DataTable)
        visible = {row["name"] for row in rows}
        for key in list(table.rows):
            if key.value not in visible:
                table.remove_row(key)
                self.table_rows.pop(key.value, None)
        for row in rows:
            cells = [row["name"], *(f"{row[field]:,}" if row[field] is not None else "—" for field in ("exported", "imported", "errors", "warnings", "log_lines")), row["status"]]
            if self.table_rows.get(row["name"]) == cells:
                continue
            self.table_rows[row["name"]] = cells
            rendered = [Text(cell) for cell in cells]
            if row["name"] not in table.rows:
                table.add_row(*rendered, key=row["name"])
            else:
                for column, cell in zip(table.columns, rendered):
                    table.update_cell(row["name"], column, cell, update_width=True)

    @on(DataTable.RowSelected, "#tables")
    def select_table(self, event: DataTable.RowSelected) -> None:
        self.selected_table = str(event.row_key.value)
        self.table_log_count = -1
        self.update_table_logs()

    def update_table_logs(self) -> None:
        if not self.job or not self.selected_table:
            return
        row = next((row for row in self.aggregation["tables"] if row["name"] == self.selected_table), None)
        if row is None or row["log_lines"] == self.table_log_count:
            return
        detail = self.job.table_logs(self.selected_table)
        self.table_log_count = detail["total"]
        self.query_one("#table-caption", Static).update(f"{detail['name']} · showing {len(detail['events'])} of {detail['total']:,} log entries")
        output = self.query_one("#table-output", RichLog)
        output.display = True
        output.clear()
        for event in detail["events"]:
            output.write(event.text)

    @on(Button.Pressed, "#stop")
    def stop_command(self) -> None:
        if self.job:
            self.job.stop()

    async def on_unmount(self) -> None:
        import asyncio
        await asyncio.to_thread(self.service.close)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Molt terminal interface")
    parser.add_argument("--log", default="", help="Import a saved log without running molt")
    args = parser.parse_args()
    MoltApp(log_path=args.log).run()


if __name__ == "__main__":
    main()
