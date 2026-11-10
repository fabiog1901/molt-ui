"""Process execution shared by both UIs; no UI framework dependencies."""

from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import shlex

LOCAL_EXECUTABLE = Path(__file__).resolve().parents[3] / "molt" / "molt"


class CliError(RuntimeError):
    """The executable could not be started or did not finish in time."""


@dataclass(frozen=True, slots=True)
class LogEntry:
    stream: str
    data: dict[str, object]


def parse_logs(output: str, stream: str) -> tuple[LogEntry, ...]:
    entries = []
    for line in output.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(LogEntry(stream, data))
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int
    logs: tuple[LogEntry, ...] = ()


class CliRunner:
    def __init__(self, executable: str, *, timeout: float = 30) -> None:
        self.executable = executable
        self.timeout = timeout

    def run(self, arguments: Sequence[str]) -> CommandResult:
        if not self.executable:
            raise CliError("Set MOLT_EXECUTABLE to the Go CLI's name or absolute path.")
        try:
            process = subprocess.run(
                [self.executable, *arguments],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliError(f"CLI timed out after {self.timeout:g} seconds.") from exc
        except OSError as exc:
            raise CliError(f"Could not start CLI: {exc}") from exc
        return CommandResult(
            process.stdout, process.stderr, process.returncode,
            parse_logs(process.stdout, "stdout") + parse_logs(process.stderr, "stderr"),
        )


class CliService:
    """Shared application operations backed by the molt executable."""

    def __init__(self, runner: CliRunner, history=None) -> None:
        from .jobs import JobManager
        from .history import RunHistory

        self.runner = runner
        self.jobs = JobManager()
        self.history = history if history is not None else RunHistory()

    def commands(self) -> list[dict]:
        from .wizard import wizard_catalog

        return wizard_catalog()

    def preview(self, command: str, options: dict[str, str | bool], *, help_only: bool = False, source_kind: str | None = None) -> dict:
        from .commands import CONNECTION_ENV, build_command
        from .wizard import normalize_options

        normalized, omitted = ({}, []) if help_only else normalize_options(command, options, source_kind=source_kind)
        arguments, environment = build_command(command, normalized, help_only=help_only, source_kind=source_kind)
        if command in {'fetch', 'verify'} and not help_only:
            for name in CONNECTION_ENV.values():
                if name not in environment and os.environ.get(name):
                    environment[name] = os.environ[name]
        argv = [self.runner.executable, *arguments]
        assignments = [f'{name}={shlex.quote(value)}' for name, value in environment.items()]
        invocation = ' '.join([*assignments, shlex.join(argv)])
        return dict(command=command, argv=argv, environment=environment, options=normalized,
                    omitted=omitted, invocation=invocation)

    def start(self, command: str, options: dict[str, str | bool], *, help_only: bool = False, source_kind: str | None = None):
        plan = self.preview(command, options, help_only=help_only, source_kind=source_kind)
        record = self.history.create(command, origin='help' if help_only else 'command',
                                     invocation=plan['invocation'], argv=plan['argv'],
                                     environment=plan['environment'], options=plan['options'])
        try:
            job = self.jobs.start(plan['argv'][0], plan['argv'][1:], plan['environment'], command)
        except CliError as exc:
            self.history.update(record['id'], {'status': 'launch_failed'}, str(exc))
            raise
        job.attach_record(record, lambda state: self.history.update(record['id'], state))
        return job

    def close(self) -> None:
        self.jobs.close()
        self.history.close()

    def import_log(self, source):
        job = self.jobs.import_log(source)
        record = self.history.create('fetch', origin='import')
        job.attach_record(record, lambda state: self.history.update(record['id'], state))
        return job

    def help(self) -> CommandResult:
        """Return molt's command help without running a migration."""
        return self.runner.run(["--help"])


def create_service() -> CliService:
    from .history import RunHistory

    executable = os.environ.get("MOLT_EXECUTABLE")
    if executable is None:
        executable = str(LOCAL_EXECUTABLE) if LOCAL_EXECUTABLE.is_file() else "molt"
    database = os.environ.get('MOLT_DATABASE', str(Path.cwd() / '.data' / 'molt-ui.sqlite3'))
    return CliService(CliRunner(executable), RunHistory(database))
