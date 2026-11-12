"""Application operations shared by the HTTP and terminal frontends."""

from __future__ import annotations

from collections.abc import Mapping
import os
from threading import Lock
from typing import TYPE_CHECKING

from molt_ui.repo.repo import RepoError
from molt_ui.repo.output import OutputCapture

from .commands import build_plan, replay_plan
from .errors import MoltError
from .models import CommandCatalog, CommandPlan, CommandResult, CommandSpec, HistoryOutput, RunRecord, RunSnapshot, TableLogs
from .runs import RunManager

if TYPE_CHECKING:
    from molt_ui.molt_process import MoltProcess
    from molt_ui.repo import Repo


class MoltService:
    def __init__(
        self,
        process: MoltProcess,
        repo: Repo,
        *,
        catalog: CommandCatalog | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._catalog = catalog
        self._process = process
        self._repo = repo
        self._runs = RunManager(process)
        self._environment = dict(os.environ if environment is None else environment)
        self._operations = Lock()
        self._closed = False

    def _require_catalog(self) -> CommandCatalog:
        if self._catalog is None:
            raise MoltError(
                "No command catalog is available in SQLite. "
                "Set MOLT_EXECUTABLE to an available molt binary and restart to generate it."
            )
        return self._catalog

    def commands(self) -> tuple[CommandSpec, ...]:
        return self._require_catalog().commands

    def preview(
        self,
        command: str,
        options: dict[str, str | bool],
        *,
        help_only: bool = False,
    ) -> CommandPlan:
        return build_plan(
            self._process.executable,
            command,
            options,
            catalog=self._require_catalog(),
            help_only=help_only,
            environment=self._environment,
        )

    def _storage(self, operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except RepoError as exc:
            raise MoltError(str(exc)) from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise MoltError("The application service has been closed.")

    def start(
        self,
        command: str,
        options: dict[str, str | bool],
        *,
        help_only: bool = False,
    ) -> RunSnapshot:
        with self._operations:
            self._ensure_open()
            self._runs.ensure_idle()
            plan = self.preview(
                command, options, help_only=help_only
            )
            return self._start_plan(plan, origin="help" if help_only else "command")

    def rerun(self, record_id: str) -> RunSnapshot:
        with self._operations:
            self._ensure_open()
            self._runs.ensure_idle()
            saved = self._storage(self._repo.get_run, record_id)
            plan = replay_plan(self._process.executable, saved)
            return self._start_plan(plan, origin=saved.origin)

    def _start_plan(self, plan: CommandPlan, *, origin: str) -> RunSnapshot:
        record = self._storage(
            self._repo.create_run,
            plan.command,
            origin=origin,
            invocation=plan.invocation,
            argv=plan.argv,
            environment=plan.environment,
            options=plan.options,
        )
        capture = OutputCapture()
        log_file = None

        def found_log_file(path: str | None) -> None:
            nonlocal log_file
            log_file = path

        def save_completion(snapshot: RunSnapshot) -> RunRecord:
            try:
                return self._repo.update_run(
                    snapshot.record.id, status=snapshot.status, returncode=snapshot.returncode,
                    summary=snapshot.aggregation["totals"], error=snapshot.history_error,
                    log_file=log_file, output=None if log_file else capture.events(),
                )
            finally:
                capture.close()

        try:
            record = self._storage(
                self._repo.update_run, record.id, status="running"
            )
            run = self._runs.start(
                plan, record=record, on_complete=save_completion,
                on_output=capture.write, on_log_file=found_log_file
            )
        except MoltError as exc:
            capture.close()
            try:
                self._repo.update_run(
                    record.id, status="launch_failed", error=str(exc)
                )
            except RepoError:
                pass
            raise
        return run.snapshot()

    def import_log(self, source) -> RunSnapshot:
        capture = OutputCapture()

        def save_import(snapshot: RunSnapshot) -> RunRecord:
            record = self._storage(
                self._repo.create_run, snapshot.command, origin="import"
            )
            return self._storage(
                self._repo.update_run,
                record.id,
                status="imported",
                summary=snapshot.aggregation["totals"], output=capture.events(), error=snapshot.history_error,
            )

        try:
            with self._operations:
                self._ensure_open()
                return self._runs.import_log(source, save=save_import, on_output=capture.write).snapshot()
        finally:
            capture.close()

    def latest_run(self) -> RunSnapshot | None:
        run = self._runs.latest()
        return run.snapshot() if run else None

    def get_run(self, run_id: str, after: int = 0) -> RunSnapshot:
        return self._runs.get(run_id).snapshot(after)

    def stop_run(self, run_id: str) -> RunSnapshot:
        run = self._runs.get(run_id)
        run.stop()
        return run.snapshot()

    def get_table_logs(self, run_id: str, table: str, limit: int = 50) -> TableLogs:
        return self._runs.get(run_id).table_logs(table, limit)

    def list_history(self, limit: int = 50) -> list[RunRecord]:
        return self._storage(self._repo.list_runs, limit)

    def get_history_output(self, record_id: str, *, before: int | None = None, limit: int = 2000) -> HistoryOutput:
        return self._storage(self._repo.get_run_output, record_id, before=before, limit=limit)

    def delete_history_record(self, record_id: str) -> int:
        with self._operations:
            self._ensure_open()
            self._runs.ensure_idle()
            deleted = self._storage(self._repo.delete_run, record_id)
            latest = self._runs.latest()
            if latest is not None:
                record = latest.snapshot().record
                if record is not None and record.id == record_id:
                    latest.attach_record(None)
            return deleted

    def clear_history(self) -> int:
        with self._operations:
            self._ensure_open()
            self._runs.ensure_idle()
            deleted = self._storage(self._repo.clear_runs)
            latest = self._runs.latest()
            if latest is not None:
                latest.attach_record(None)
            return deleted

    def get_history_record(self, record_id: str) -> RunRecord:
        return self._storage(self._repo.get_run, record_id)

    def help(self) -> CommandResult:
        return self._process.run(["--help"])

    def close(self) -> None:
        with self._operations:
            if self._closed:
                return
            self._closed = True
            self._runs.close()
            self._repo.close()
