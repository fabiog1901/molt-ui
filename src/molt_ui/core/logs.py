"""Shared JSON-line parsing for live processes and imported logs."""

import json

from .models import LogEntry


def parse_line(text: str) -> dict[str, object] | None:
    try:
        data = json.loads(text)
    except ValueError, RecursionError:
        return None
    return data if isinstance(data, dict) else None


def parse_logs(output: str, stream: str) -> tuple[LogEntry, ...]:
    return tuple(
        LogEntry(stream=stream, data=data)
        for line in output.splitlines()
        if (data := parse_line(line)) is not None
    )
