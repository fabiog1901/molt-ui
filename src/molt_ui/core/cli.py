"""Process execution shared by both UIs; no UI framework dependencies."""

from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

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

    def __init__(self, runner: CliRunner) -> None:
        from .jobs import JobManager

        self.runner = runner
        self.jobs = JobManager()

    def commands(self) -> list[dict]:
        from .catalog import COMMANDS

        return COMMANDS

    def start(self, command: str, options: dict[str, str | bool], *, help_only: bool = False):
        from .commands import build_command

        arguments, environment = build_command(command, options, help_only=help_only)
        return self.jobs.start(self.runner.executable, arguments, environment, command)

    def close(self) -> None:
        self.jobs.close()

    def import_log(self, source):
        return self.jobs.import_log(source)

    def help(self) -> CommandResult:
        """Return molt's command help without running a migration."""
        return self.runner.run(["--help"])


def create_service() -> CliService:
    executable = os.environ.get("MOLT_EXECUTABLE")
    if executable is None:
        executable = str(LOCAL_EXECUTABLE) if LOCAL_EXECUTABLE.is_file() else "molt"
    return CliService(CliRunner(executable))
