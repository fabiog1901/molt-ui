"""The only runtime adapter that launches or controls the molt executable."""

from collections.abc import Callable, Mapping, Sequence
import os
import signal
import subprocess
from threading import Event, Lock, Thread

from .core.errors import MoltError
from .core.logs import parse_logs
from .core.models import CommandResult


class ProcessHandle:
    """Own a child process, its pipe readers, and termination escalation."""

    def __init__(
        self,
        process: subprocess.Popen,
        on_output: Callable[[str, str], None],
        on_exit: Callable[[int, bool], None],
    ) -> None:
        self._process = process
        self._on_output = on_output
        self._on_exit = on_exit
        self._lock = Lock()
        self._finished = Event()
        self._drained = Event()
        self._stop_requested = False
        self._thread = Thread(target=self._collect, daemon=True)
        self._thread.start()

    def _read(self, pipe, stream: str) -> None:
        try:
            while text := pipe.readline(16384):
                self._on_output(text.rstrip("\r\n"), stream)
        finally:
            pipe.close()

    def _collect(self) -> None:
        readers = [
            Thread(target=self._read, args=(pipe, stream), daemon=True)
            for pipe, stream in (
                (self._process.stdout, "stdout"),
                (self._process.stderr, "stderr"),
            )
        ]
        try:
            for reader in readers:
                reader.start()
            returncode = self._process.wait()
            for reader in readers:
                reader.join()
            self._drained.set()
            with self._lock:
                stopped = self._stop_requested
            self._on_exit(returncode, stopped)
        finally:
            self._finished.set()

    def _terminate(self, *, force: bool = False) -> None:
        try:
            if os.name == "posix":
                os.killpg(
                    self._process.pid, signal.SIGKILL if force else signal.SIGTERM
                )
            elif force:
                self._process.kill()
            else:
                self._process.terminate()
        except ProcessLookupError:
            pass

    def stop(self) -> None:
        with self._lock:
            if (
                self._finished.is_set()
                or self._drained.is_set()
                or self._stop_requested
            ):
                return
            self._stop_requested = True
        self._terminate()
        Thread(target=self._kill_later, daemon=True).start()

    def _kill_later(self) -> None:
        if not self._finished.wait(2) and not self._drained.is_set():
            self._terminate(force=True)

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    def close(self) -> None:
        self.stop()
        self.wait(5)


class MoltProcess:
    """Execute argv directly; expose output without application or storage policy."""

    def __init__(
        self,
        executable: str,
        *,
        timeout: float = 30,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = executable
        self.timeout = timeout
        self._environment = dict(os.environ if environment is None else environment)

    def _env(self, overrides: Mapping[str, str] | None) -> dict[str, str]:
        return {**self._environment, **(overrides or {})}

    def run(self, arguments: Sequence[str]) -> CommandResult:
        if not self.executable:
            raise MoltError(
                "Set MOLT_EXECUTABLE to the Go CLI's name or absolute path."
            )
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
                env=self._env(None),
            )
        except subprocess.TimeoutExpired as exc:
            raise MoltError(f"CLI timed out after {self.timeout:g} seconds.") from exc
        except OSError as exc:
            raise MoltError(f"Could not start CLI: {exc}") from exc
        return CommandResult(
            stdout=process.stdout,
            stderr=process.stderr,
            returncode=process.returncode,
            logs=parse_logs(process.stdout, "stdout")
            + parse_logs(process.stderr, "stderr"),
        )

    def start(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        on_output: Callable[[str, str], None],
        on_exit: Callable[[int, bool], None],
    ) -> ProcessHandle:
        if not self.executable:
            raise MoltError(
                "Set MOLT_EXECUTABLE to the Go CLI's name or absolute path."
            )
        try:
            process = subprocess.Popen(
                [self.executable, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=self._env(environment),
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            raise MoltError(f"Could not start CLI: {exc}") from exc
        return ProcessHandle(process, on_output, on_exit)
