"""Bounded-memory output capture and paged reading of Molt log files."""

from collections import deque
from collections.abc import Iterator
import json
from pathlib import Path
from tempfile import SpooledTemporaryFile
from threading import Lock

from molt_ui.core.logs import parse_line
from molt_ui.core.models import HistoryOutput, OutputEvent


class OutputCapture:
    """Spill large stdout/stderr captures to temporary disk until completion."""

    def __init__(self) -> None:
        self._stream = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+t", encoding="utf-8")
        self._lock = Lock()

    def write(self, event: OutputEvent) -> None:
        with self._lock:
            self._stream.write(event.model_dump_json(exclude={"data"}) + "\n")

    def events(self) -> Iterator[OutputEvent]:
        with self._lock:
            self._stream.seek(0)
        while True:
            with self._lock:
                line = self._stream.readline()
            if not line:
                break
            yield OutputEvent(**json.loads(line), data=None)

    def close(self) -> None:
        with self._lock:
            self._stream.close()


def read_log_file(path: str, *, before: int | None, limit: int) -> HistoryOutput:
    events = deque(maxlen=limit)
    total = 0
    with Path(path).open(encoding="utf-8-sig", errors="replace") as source:
        while text := source.readline(16384):
            total += 1
            if before is None or total < before:
                text = text.rstrip("\r\n")
                events.append((total, text))
    return HistoryOutput(
        source="file", log_file=path, total=total,
        events=tuple(OutputEvent(sequence=sequence, stream="log", text=text, data=parse_line(text))
                     for sequence, text in events),
        next_before=events[0][0] if events and events[0][0] > 1 else None,
    )
