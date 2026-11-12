"""The only runtime adapter that launches or controls the molt executable."""

from collections.abc import Callable, Mapping, Sequence
import logging
import os
from pathlib import Path
import signal
import subprocess
from tempfile import SpooledTemporaryFile
from threading import Event, Lock, Thread

from .core.errors import MoltError
from .core.logs import parse_logs
from .core.models import CommandResult


class LogFileTracker:
    """Observe explicit log files or a single new command-{datetime}.log file."""

    def __init__(self, arguments: Sequence[str]):
        self.directory = Path.cwd()
        self.explicit = None
        for index, argument in enumerate(arguments):
            if argument.startswith("--log-file="):
                self.explicit = argument.partition("=")[2]
            elif argument == "--log-file" and index + 1 < len(arguments):
                self.explicit = arguments[index + 1]
        self.pattern = f"{arguments[0]}-*.log" if arguments else "*.log"
        self.before = self._files()

    def _files(self):
        if self.explicit == "stdout":
            return {}
        paths = [self.directory / self.explicit] if self.explicit else self.directory.glob(self.pattern)
        found = {}
        for path in paths:
            try:
                if path.is_file():
                    stat = path.stat()
                    found[str(path.resolve())] = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
        return found

    def created_file(self) -> str | None:
        try:
            changed = [path for path, state in self._files().items() if self.before.get(path) != state]
            return changed[0] if len(changed) == 1 else None
        except OSError:
            return None


class OutputLogTee:
    """Append process output live, buffering until Molt creates its log file."""

    def __init__(self, tracker: LogFileTracker) -> None:
        self.tracker = tracker
        self.path: str | None = None
        self.failed = False
        self._pending = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
        self._destination = None
        self._lock = Lock()
        self._done = Event()
        self._watcher = Thread(target=self._watch, daemon=True)
        self._watcher.start()

    def _append(self, text: bytes) -> None:
        remaining = memoryview(text)
        while remaining:
            written = self._destination.write(remaining)
            if not written:
                raise OSError("Log file write made no progress")
            remaining = remaining[written:]

    def _connect(self) -> None:
        if self._destination is not None or self.failed:
            return
        path = self.tracker.created_file()
        if not path:
            return
        # O_APPEND makes each write target the current end, even while Molt
        # is writing. Do not create a replacement if its log disappeared.
        descriptor = os.open(path, os.O_RDWR | os.O_APPEND)
        self._destination = os.fdopen(descriptor, "r+b", buffering=0)
        self.path = path
        size = self._destination.seek(0, 2)
        self._needs_newline = False
        if size:
            self._destination.seek(-1, 2)
            self._needs_newline = self._destination.read(1) != b"\n"
        self._pending.seek(0)
        while chunk := self._pending.read(65536):
            self._write_connected(chunk)
        self._pending.close()

    def _write_connected(self, text: bytes) -> None:
        if self._needs_newline:
            self._append(b"\n")
            self._needs_newline = False
        self._append(text)

    def _fail(self, exc: OSError) -> None:
        self.failed = True
        logging.getLogger(__name__).warning(
            "Could not append process output to Molt log file; saving output in SQLite instead: %s", exc
        )

    def write(self, text: str, stream: str = "stdout") -> None:
        # Molt already writes its JSON log lines to the file. Only tee the
        # additional plain stdout output and all stderr. Live capture keeps
        # every line from both streams.
        if stream == "stdout" and text.startswith("{"):
            return
        with self._lock:
            if self.failed:
                return
            try:
                self._connect()
                data = (text + "\n").encode("utf-8")
                if self._destination is None:
                    self._pending.write(data)
                else:
                    self._write_connected(data)
            except OSError as exc:
                self._fail(exc)

    def _watch(self) -> None:
        # A file may appear after the last stdout line, while Molt keeps running.
        while not self._done.wait(.05):
            with self._lock:
                try:
                    self._connect()
                except OSError as exc:
                    self._fail(exc)
                if self._destination is not None or self.failed:
                    return

    def close(self) -> str | None:
        self._done.set()
        self._watcher.join()
        with self._lock:
            try:
                self._connect()
            except OSError as exc:
                self._fail(exc)
            finally:
                if self._destination is not None:
                    self._destination.close()
                self._pending.close()
        return None if self.failed else self.path


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
        on_log_file: Callable[[str | None], None] | None = None,
    ) -> ProcessHandle:
        if not self.executable:
            raise MoltError(
                "Set MOLT_EXECUTABLE to the Go CLI's name or absolute path."
            )
        tracker = LogFileTracker(arguments) if on_log_file is not None else None
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
        tee = OutputLogTee(tracker) if tracker is not None and tracker.explicit != "stdout" else None

        def output(text: str, stream: str):
            if tee is not None:
                tee.write(text, stream)
            on_output(text, stream)

        def finished(returncode: int, stopped: bool):
            if tracker is not None:
                on_log_file(tee.close() if tee is not None else None)
            on_exit(returncode, stopped)

        return ProcessHandle(process, output, finished)
