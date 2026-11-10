"""Application operations shared by the HTTP and terminal frontends."""

from __future__ import annotations

from collections.abc import Mapping
import os
from threading import Lock
from typing import TYPE_CHECKING

from molt_ui.repo.repo import RepoError

from .commands import build_plan
from .errors import MoltError
from .models import CommandPlan, CommandResult, RunRecord, RunSnapshot, TableLogs
from .runs import RunManager
from .wizard import wizard_catalog

if TYPE_CHECKING:
    from molt_ui.molt_process import MoltProcess
    from molt_ui.repo import Repo


class MoltService:
    def __init__(
        self,
        process: MoltProcess,
        repo: Repo,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._process = process
        self._repo = repo
        self._runs = RunManager(process)
        self._environment = dict(os.environ if environment is None else environment)
        self._operations = Lock()
        self._closed = False

    def commands(self) -> list[dict]:
        return wizard_catalog(environment=self._environment)

    def preview(
        self,
        command: str,
        options: dict[str, str | bool],
        *,
        help_only: bool = False,
        source_kind: str | None = None,
    ) -> CommandPlan:
        return build_plan(
            self._process.executable,
            command,
            options,
            help_only=help_only,
            source_kind=source_kind,
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

    def _save_completion(self, snapshot: RunSnapshot) -> RunRecord:
        return self._repo.update_run(
            snapshot.record.id,
            status=snapshot.status,
            returncode=snapshot.returncode,
            summary=snapshot.aggregation["totals"],
        )

    def start(
        self,
        command: str,
        options: dict[str, str | bool],
        *,
        help_only: bool = False,
        source_kind: str | None = None,
    ) -> RunSnapshot:
        with self._operations:
            self._ensure_open()
            self._runs.ensure_idle()
            plan = self.preview(
                command, options, help_only=help_only, source_kind=source_kind
            )
            record = self._storage(
                self._repo.create_run,
                command,
                origin="help" if help_only else "command",
                invocation=plan.invocation,
                argv=plan.argv,
                environment=plan.environment,
                options=plan.options,
            )
            try:
                record = self._storage(
                    self._repo.update_run, record.id, status="running"
                )
                run = self._runs.start(
                    plan, record=record, on_complete=self._save_completion
                )
            except MoltError as exc:
                try:
                    self._repo.update_run(
                        record.id, status="launch_failed", error=str(exc)
                    )
                except RepoError:
                    pass
                raise
            return run.snapshot()

    def import_log(self, source) -> RunSnapshot:
        def save_import(snapshot: RunSnapshot) -> RunRecord:
            record = self._storage(
                self._repo.create_run, snapshot.command, origin="import"
            )
            return self._storage(
                self._repo.update_run,
                record.id,
                status="imported",
                summary=snapshot.aggregation["totals"],
            )

        with self._operations:
            self._ensure_open()
            return self._runs.import_log(source, save=save_import).snapshot()

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
