from io import StringIO
from pathlib import Path
import sys
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandPlan
from molt_ui.core.service import MoltService
from molt_ui.frontends.api.app import create_app
from molt_ui.molt_process import LogFileTracker, MoltProcess, OutputLogTee
from molt_ui.repo import Repo


def wait_for(service, run):
    for _ in range(500):
        result = service.get_run(run.id)
        if result.status != "running":
            return result
        time.sleep(.01)
    raise AssertionError("Job did not finish")


def test_full_stdout_and_stderr_survive_restart_beyond_live_buffer(tmp_path):
    database = str(tmp_path / "history.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(database))
    code = "import sys; [print('row '+str(i)+' '+('x'*300)) for i in range(5000)]; print('last error', file=sys.stderr)"
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code), options={}, environment={}, invocation="test")
    with patch.object(service, "preview", return_value=plan):
        completed = wait_for(service, service.start("fetch", {}))
    assert len(completed.events) == 2000
    record_id = completed.record.id
    service.close()
    service = MoltService(MoltProcess("/unused"), Repo(database))
    with TestClient(create_app(service)) as client:
        page = client.get(f"/api/history/{record_id}/output").json()
        assert page["source"] == "captured"
        assert page["total"] == 5001
        assert len(page["events"]) == 2000
        events = list(page["events"])
        while page["next_before"]:
            page = client.get(f"/api/history/{record_id}/output?before={page['next_before']}").json()
            events = page["events"] + events
        assert len(events) == 5001
        assert {event["sequence"] for event in events} == set(range(1, 5002))
        assert any(event["stream"] == "stderr" and event["text"] == "last error" for event in events)
        assert any(event["text"].startswith("row 0 ") for event in events)
        assert client.get(f"/api/history/{record_id}/output?limit=2001").status_code == 422
        assert client.get("/api/history/unknown/output").status_code == 404


def test_created_file_includes_stdout_and_is_read_on_demand(tmp_path):
    path = tmp_path / "fetch.log"
    repo = Repo()
    service = MoltService(MoltProcess(sys.executable), repo)
    code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('file line one\\nfile line two\\n'); print('stdout only')"
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code, str(path), f"--log-file={path}"),
                       options={"log-file": str(path)}, environment={}, invocation="test")
    with patch.object(service, "preview", return_value=plan):
        completed = wait_for(service, service.start("fetch", {}))
    assert completed.record.log_file == str(path)
    assert repo._connection.execute("SELECT COUNT(*) FROM run_output").fetchone()[0] == 0
    page = service.get_history_output(completed.record.id)
    assert page.source == "file"
    assert [event.text for event in page.events] == ["file line one", "file line two", "stdout only"]
    assert any(event.text == "stdout only" for event in completed.events)
    with path.open("a") as output:
        output.write("later file line\n")
    assert service.get_history_output(completed.record.id).events[-1].text == "later file line"
    path.unlink()
    with pytest.raises(MoltError, match="Could not open saved log file"):
        service.get_history_output(completed.record.id)
    service.close()


def test_stdout_append_keeps_duplicates_and_handles_missing_final_newline(tmp_path):
    path = tmp_path / "fetch.log"
    service = MoltService(MoltProcess(sys.executable), Repo())
    code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('shared line'); print('shared line'); print('stdout only')"
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code, str(path), f"--log-file={path}"),
                       options={"log-file": str(path)}, environment={}, invocation="test")
    with patch.object(service, "preview", return_value=plan):
        completed = wait_for(service, service.start("fetch", {}))
    assert path.read_text() == "shared line\nshared line\nstdout only\n"
    assert service.get_history_output(completed.record.id).total == 3
    service.close()


def test_stdout_append_failure_saves_output_in_sqlite(tmp_path, caplog):
    path = tmp_path / "fetch.log"
    service = MoltService(MoltProcess(sys.executable), Repo())
    code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('file line\\n'); print('stdout only')"
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code, str(path), f"--log-file={path}"),
                       options={"log-file": str(path)}, environment={}, invocation="test")
    with patch.object(service, "preview", return_value=plan), patch(
        "molt_ui.molt_process.OutputLogTee._append", side_effect=OSError("not writable")
    ):
        completed = wait_for(service, service.start("fetch", {}))
    assert completed.status == "succeeded"
    assert completed.record.log_file is None
    assert "Could not append process output" in caplog.text
    page = service.get_history_output(completed.record.id)
    assert page.source == "captured"
    assert [event.text for event in page.events] == ["stdout only"]
    service.close()


@pytest.mark.parametrize("create_file", [True, False])
def test_json_stdout_is_only_excluded_from_file_tee(tmp_path, create_file):
    path = tmp_path / "fetch.log"
    line = '{"level":"info","message":"shared log"}'
    service = MoltService(MoltProcess(sys.executable), Repo())
    code = f"""
import pathlib
line = {line!r}
if {create_file!r}:
    pathlib.Path({str(path)!r}).write_text(line + '\\n')
print(line)
print('plain stdout')
"""
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code, f"--log-file={path}"),
                       options={"log-file": str(path)}, environment={}, invocation="test")
    try:
        with patch.object(service, "preview", return_value=plan):
            completed = wait_for(service, service.start("fetch", {}))
        assert [event.text for event in completed.events] == [line, "plain stdout"]
        page = service.get_history_output(completed.record.id)
        assert [event.text for event in page.events] == [line, "plain stdout"]
        assert page.source == ("file" if create_file else "captured")
        if create_file:
            assert path.read_text() == line + "\nplain stdout\n"
    finally:
        service.close()


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_is_in_log_while_process_is_still_running(tmp_path, stream):
    path = tmp_path / "fetch.log"
    release = tmp_path / "release"
    service = MoltService(MoltProcess(sys.executable), Repo())
    code = """
import pathlib, sys, time
path, release = map(pathlib.Path, sys.argv[1:3])
with path.open('a') as log:
    log.write('file before\\n')
    log.flush()
    print('live output', file=STREAM, flush=True)
    print('{"message":"structured output"}', file=STREAM, flush=True)
    deadline = time.monotonic() + 10
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    log.write('file after\\n')
""".replace("STREAM", f"sys.{stream}")
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code, str(path), str(release),
                       f"--log-file={path}"), options={"log-file": str(path)}, environment={}, invocation="test")
    try:
        with patch.object(service, "preview", return_value=plan):
            run = service.start("fetch", {})
        for _ in range(500):
            expected = '{"message":"structured output"}\n' if stream == "stderr" else "live output\n"
            if path.exists() and expected in path.read_text():
                break
            time.sleep(.01)
        else:
            pytest.fail(f"{stream} was not appended while the child was running")
        assert service.get_run(run.id).status == "running"
        release.touch()
        completed = wait_for(service, run)
        structured = '{"message":"structured output"}\n' if stream == "stderr" else ""
        assert path.read_text() == "file before\nlive output\n" + structured + "file after\n"
        assert service.get_history_output(completed.record.id).total == (4 if stream == "stderr" else 3)
    finally:
        release.touch()
        service.close()


def test_automatic_log_appearance_flushes_early_stdout_without_waiting_for_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tee = OutputLogTee(LogFileTracker(["fetch"]))
    path = tmp_path / "fetch-new.log"
    try:
        tee.write('{"message":"already logged"}')
        tee.write("early stdout")
        path.write_text("first file line\n")
        for _ in range(500):
            if "early stdout\n" in path.read_text():
                break
            time.sleep(.01)
        else:
            pytest.fail("Buffered stdout was not flushed when the log appeared")
        tee.write("later stdout")
        assert path.read_text() == "first file line\nearly stdout\nlater stdout\n"
    finally:
        saved_path = tee.close()
    assert saved_path == str(path)


def test_no_file_created_falls_back_to_saved_stdout(tmp_path):
    path = tmp_path / "never-created.log"
    service = MoltService(MoltProcess(sys.executable), Repo())
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", "print('captured output')", f"--log-file={path}"),
                       options={"log-file": str(path)}, environment={}, invocation="test")
    with patch.object(service, "preview", return_value=plan):
        completed = wait_for(service, service.start("fetch", {}))
    assert completed.record.log_file is None
    assert service.get_history_output(completed.record.id).events[0].text == "captured output"
    service.close()


def test_import_output_is_persisted_in_full_and_deleted_with_history(tmp_path):
    database = str(tmp_path / "imports.sqlite3")
    service = MoltService(MoltProcess("/unused"), Repo(database))
    imported = service.import_log(StringIO("original line\n" * 2100))
    record_id = imported.record.id
    service.close()
    repo = Repo(database)
    assert repo.get_run_output(record_id).total == 2100
    assert repo.get_run_output(record_id, before=101).events[0].sequence == 1
    assert repo.clear_runs() == 1
    assert repo._connection.execute("SELECT COUNT(*) FROM run_output").fetchone()[0] == 0
    repo.close()


def test_automatic_log_discovery_ignores_old_files_and_ambiguous_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fetch-old.log").write_text("older job")
    tracker = LogFileTracker(["fetch"])
    path = tmp_path / "fetch-new.log"
    path.write_text("new job")
    assert tracker.created_file() == str(path)
    (tmp_path / "fetch-another.log").write_text("ambiguous")
    assert tracker.created_file() is None
    stdout_only = LogFileTracker(["fetch", "--log-file=stdout"])
    (tmp_path / "fetch-later.log").write_text("other process")
    assert stdout_only.created_file() is None
