from io import StringIO
from pathlib import Path
import shlex
import sys
import json
import os
import subprocess
import time
from unittest.mock import patch

import pytest

from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandPlan
from molt_ui.core.service import MoltService
from molt_ui.molt_process import MoltProcess, OutputLogTee
from molt_ui.repo import Repo


def wait_for(service, run):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = service.get_run(run.id)
        if state.status != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("Run did not finish")


def test_exact_credentials_and_invocation_roundtrip_storage(command_catalog, tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess("/path with spaces/molt"), Repo(path), catalog=command_catalog)
    source = "postgres://user:p@ss$word@source/db?sslmode=require"
    options = {
        "source": source,
        "target": "postgres://target/db",
        "direct-copy": True,
        "table-filter": "public.weird table; $(echo nope)",
    }
    plan = service.preview("fetch", options)
    assert source in plan.invocation
    assert shlex.split(plan.invocation)[0] == "MOLT_SOURCE=" + source
    with patch(
        "molt_ui.molt_process.subprocess.Popen",
        side_effect=FileNotFoundError("missing binary"),
    ):
        with pytest.raises(MoltError):
            service.start("fetch", options)
    saved = Repo(path).list_runs()[0]
    assert saved.invocation == plan.invocation
    assert saved.environment["MOLT_SOURCE"] == source
    assert saved.argv == list(plan.argv)
    assert saved.options == options
    assert saved.status == "launch_failed"
    assert saved.finished_at and saved.error
    if sys.platform != "win32":
        assert Path(path).stat().st_mode & 0o777 == 0o600
    service.close()


def test_completion_is_persisted_without_polling(command_catalog, tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(path), catalog=command_catalog)
    plan = CommandPlan(
        command="fetch",
        argv=(sys.executable, "--help"),
        environment={},
        options={},
        invocation=shlex.join([sys.executable, "--help"]),
    )
    with patch.object(service, "preview", return_value=plan):
        run = service.start("fetch", {}, help_only=True)
    # Inspect storage, without using get_run to trigger any persistence work.
    deadline = time.monotonic() + 5
    observer = Repo(path)
    while time.monotonic() < deadline:
        record = observer.get_run(run.record.id)
        if record.status == "succeeded":
            break
        time.sleep(0.01)
    assert record.status == "succeeded"
    assert record.origin == "help"
    assert record.returncode == 0
    assert record.summary["log_lines"] > 0
    assert record.finished_at
    assert record.invocation == plan.invocation
    observer.close()
    service.close()


@pytest.mark.parametrize("code, diagnostic", [
    ('import sys; print("connection refused", file=sys.stderr); sys.exit(2)', "connection refused"),
    ('import sys; print(\'{"level":"fatal","message":"migration failed"}\'); '
     'print("later output\\n" * 2100); sys.exit(3)', "migration failed"),
    ('raise SystemExit(4)', "Molt exited with code 4."),
])
def test_failed_process_persists_diagnostic_and_output_without_polling(tmp_path, code, diagnostic):
    database = str(tmp_path / "failure.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(database))
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", code),
                       environment={}, options={}, invocation="test process")
    try:
        with patch.object(service, "preview", return_value=plan):
            run = service.start("fetch", {})
        # Waiting on the process, rather than polling, must still save completion.
        assert service._runs.get(run.id).handle.wait(5)
        record = service.get_history_record(run.record.id)
        assert record.status == "failed"
        assert record.returncode != 0
        assert record.finished_at
        assert diagnostic in record.error
        snapshot = service.get_run(run.id)
        assert snapshot.error == record.error
        assert snapshot.history_error is None
        assert service.get_history_output(record.id).total > 0 or record.returncode == 4
    finally:
        service.close()
    restarted = MoltService(MoltProcess(sys.executable), Repo(database))
    try:
        assert restarted.get_history_record(record.id) == record
    finally:
        restarted.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process ownership recovery")
def test_restart_recovers_jobs_from_a_crashed_app(tmp_path):
    database = str(tmp_path / "crashed.sqlite3")
    code = """import json, os, sys
from molt_ui.repo import Repo
repo = Repo(sys.argv[1])
starting = repo.create_run('fetch', origin='command', argv=['molt', 'fetch'],
                           log_name='fetch-2026-11-12T12.00.00Z.log')
running = repo.create_run('verify', origin='command', argv=['molt', 'verify'],
                         log_name='verify-2026-11-12T12.00.01Z.log')
repo.update_run(running.id, status='running')
print(json.dumps([starting.id, running.id]), flush=True)
os._exit(1)
"""
    child = subprocess.run([sys.executable, "-c", code, database],
                           capture_output=True, text=True, timeout=5)
    assert child.returncode == 1, child.stderr
    records = json.loads(child.stdout)
    service = MoltService(MoltProcess(sys.executable), Repo(database))
    try:
        for record_id in records:
            record = service.get_history_record(record_id)
            assert record.status == "interrupted"
            assert record.finished_at
            assert record.returncode is None
            assert "outcome is unknown" in record.error
    finally:
        service.close()


def test_second_service_does_not_interrupt_a_live_job(tmp_path):
    database = str(tmp_path / "shared.sqlite3")
    first = MoltService(MoltProcess(sys.executable), Repo(database))
    second = None
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", "import time; time.sleep(30)"),
                       environment={}, options={}, invocation="test process")
    try:
        with patch.object(first, "preview", return_value=plan):
            run = first.start("fetch", {})
        second = MoltService(MoltProcess(sys.executable), Repo(database))
        assert second.get_history_record(run.record.id).status == "running"
        first.close()
        assert second.get_history_record(run.record.id).status == "stopped"
    finally:
        first.close()
        if second is not None:
            second.close()


def test_log_finalization_failure_does_not_leave_failed_process_running():
    service = MoltService(MoltProcess(sys.executable), Repo())
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c",
                       'import sys; print("problem", file=sys.stderr); sys.exit(2)'),
                       environment={}, options={}, invocation="test process")
    close = OutputLogTee.close

    def failed_close(tee):
        close(tee)
        raise OSError("disk error")

    try:
        with patch.object(OutputLogTee, "close", failed_close):
            with patch.object(service, "preview", return_value=plan):
                run = service.start("fetch", {})
            snapshot = wait_for(service, run)
        assert snapshot.status == "failed"
        assert snapshot.record.returncode == 2
        assert "problem" in snapshot.record.error
        assert service.get_history_output(snapshot.record.id).events[0].text == "problem"
    finally:
        service.close()


def test_preview_is_nonexecuting_and_preserves_submitted_options(command_catalog):
    service = MoltService(MoltProcess("molt"), Repo(), catalog=command_catalog)
    with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
        plan = service.preview(
            "fetch",
            {
                "source": "postgres://source/db",
                "target": "postgres://target/db",
                "direct-copy": True,
                "bucket-path": "s3://bucket",
                "assume-role": "role",
                "oracle-application-users": "user",
            },
        )
        spawn.assert_not_called()
    assert plan.omitted == ()
    assert "--bucket-path=s3://bucket" in plan.argv
    assert "--oracle-application-users=user" in plan.argv
    assert plan.options["bucket-path"] == "s3://bucket"
    assert service.list_history() == []
    service.close()


def test_import_records_have_no_fabricated_command(command_catalog, tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess("molt"), Repo(path), catalog=command_catalog)
    run = service.import_log(
        StringIO(
            '{"table":"public.actor","num_rows":200,"message":"data extraction from source complete"}\n'
        )
    )
    record = service.get_history_record(run.record.id)
    assert record.status == "imported"
    assert record.invocation is None
    assert record.origin == "import"
    assert record.returncode is None
    assert record.summary["exported"] == 200
    service.close()


def test_storage_failure_prevents_launch_and_failed_import_preserves_latest_run(command_catalog):
    from molt_ui.repo.repo import RepoError

    repo = Repo()
    service = MoltService(MoltProcess("molt"), repo, catalog=command_catalog)
    original = service.import_log(StringIO("original log\n"))
    with patch.object(repo, "create_run", side_effect=RepoError("disk full")):
        with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
            with pytest.raises(MoltError, match="disk full"):
                service.start(
                    "fetch",
                    {
                        "source": "postgres://source/db",
                        "target": "postgres://target/db",
                    },
                )
            with pytest.raises(MoltError, match="disk full"):
                service.import_log(StringIO("replacement log\n"))
            spawn.assert_not_called()
    assert service.latest_run().id == original.id
    assert len(service.list_history()) == 1
    service.close()


def test_close_stops_the_live_run_and_persists_its_final_status(command_catalog, tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(path), catalog=command_catalog)
    plan = CommandPlan(
        command="fetch",
        argv=(sys.executable, "-c", "import time; time.sleep(30)"),
        options={},
        environment={},
        invocation="python test",
    )
    with patch.object(service, "preview", return_value=plan):
        run = service.start("fetch", {})
    with pytest.raises(MoltError, match="already running"):
        service.start("verify", {})
    assert len(service.list_history()) == 1
    service.close()
    observer = Repo(path)
    record = observer.get_run(run.record.id)
    assert record.status == "stopped"
    assert record.returncode is not None
    assert record.finished_at
    observer.close()
    service.close()


def test_service_instances_keep_separate_injected_catalogs():
    from molt_ui.core.models import CommandCatalog, CommandSpec, OptionSpec

    def catalog_for(environment_variable):
        return CommandCatalog(schema_version=1, commands=(
            CommandSpec(id="future", arguments=("future",), options=(
                OptionSpec(name="connection", kind="string", description="Connection", default="",
                           environment_variable=environment_variable),
            )),
        ))

    first_catalog = catalog_for("MOLT_FIRST")
    second_catalog = catalog_for("MOLT_SECOND")
    first = MoltService(MoltProcess("molt"), Repo(), catalog=first_catalog, environment={})
    second = MoltService(MoltProcess("molt"), Repo(), catalog=second_catalog, environment={})
    assert first.commands() == first_catalog.commands
    assert second.commands() == second_catalog.commands
    assert first.preview("future", {"connection": "one"}).environment == {"MOLT_FIRST": "one"}
    assert second.preview("future", {"connection": "two"}).environment == {"MOLT_SECOND": "two"}
    first.close()
    second.close()


def test_rerun_after_restart_preserves_saved_arguments_and_connections(tmp_path):
    database = str(tmp_path / "rerun.sqlite3")
    repo = Repo(database)
    code = "import os,sys; print(os.environ['MOLT_SOURCE']); print(sys.argv[1])"
    literal = "--table-filter=users; echo literal"
    original = repo.create_run(
        "fetch", origin="command", invocation="display text is not executed",
        argv=("/old/location/molt", "-c", code, literal),
        environment={"MOLT_SOURCE": "saved-connection"},
        options={"direct-copy": False, "table-filter": literal},
    )
    original = repo.update_run(original.id, status="succeeded", returncode=0, summary={"exported": 200})
    repo.close()
    service = MoltService(
        MoltProcess(sys.executable, environment={"MOLT_SOURCE": "changed-connection"}),
        Repo(database), environment={"MOLT_SOURCE": "changed-connection"},
    )
    state = wait_for(service, service.rerun(original.id))
    assert state.status == "succeeded"
    assert state.record.id != original.id
    assert state.record.argv == [sys.executable, *original.argv[1:]]
    assert state.record.environment == original.environment
    assert state.record.options == original.options
    assert "saved-connection" in [event.text for event in state.events]
    assert literal in [event.text for event in state.events]
    assert service.get_history_record(original.id) == original
    assert len(service.list_history()) == 2
    service.close()


def test_rerun_respects_single_active_job_and_does_not_create_extra_records():
    repo = Repo()
    saved = repo.create_run("fetch", origin="command", argv=(sys.executable, "--help"))
    service = MoltService(MoltProcess(sys.executable), repo)
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", "import time; time.sleep(30)"),
                       environment={}, options={}, invocation="test process")
    with patch.object(service, "preview", return_value=plan):
        service.start("fetch", {})
    before = len(service.list_history())
    with pytest.raises(MoltError, match="already running"):
        service.rerun(saved.id)
    assert len(service.list_history()) == before
    service.close()


def test_failed_rerun_is_a_new_failed_attempt_and_preserves_original():
    repo = Repo()
    original = repo.create_run("fetch", origin="command", argv=("molt", "fetch"))
    original = repo.update_run(original.id, status="succeeded", returncode=0)
    service = MoltService(MoltProcess("/missing/molt"), repo)
    with patch("molt_ui.molt_process.subprocess.Popen", side_effect=FileNotFoundError("missing")):
        with pytest.raises(MoltError):
            service.rerun(original.id)
    records = service.list_history()
    assert len(records) == 2
    assert next(record for record in records if record.id != original.id).status == "launch_failed"
    assert service.get_history_record(original.id) == original
    service.close()


@pytest.mark.parametrize("origin, argv", [("import", ()), ("command", ())])
def test_history_without_an_executable_command_cannot_be_rerun(origin, argv):
    repo = Repo()
    saved = repo.create_run("fetch", origin=origin, argv=argv)
    service = MoltService(MoltProcess(sys.executable), repo)
    with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
        with pytest.raises(ValueError, match="no saved command"):
            service.rerun(saved.id)
        spawn.assert_not_called()
    assert len(service.list_history()) == 1
    service.close()


def test_clear_history_keeps_current_output_but_detaches_deleted_record():
    service = MoltService(MoltProcess(sys.executable), Repo())
    original = service.import_log(StringIO("existing output\n"))
    assert service.clear_history() == 1
    assert service.list_history() == []
    current = service.get_run(original.id)
    assert current.events == original.events
    assert current.aggregation == original.aggregation
    assert current.record is None
    with pytest.raises(KeyError):
        service.rerun(original.record.id)
    service.close()


def test_clear_history_is_blocked_while_a_job_is_running():
    repo = Repo()
    service = MoltService(MoltProcess(sys.executable), repo)
    plan = CommandPlan(command="fetch", argv=(sys.executable, "-c", "import time; time.sleep(30)"),
                       environment={}, options={}, invocation="test process")
    with patch.object(service, "preview", return_value=plan):
        job = service.start("fetch", {})
    with pytest.raises(MoltError, match="already running"):
        service.clear_history()
    with pytest.raises(MoltError, match="already running"):
        service.delete_history_record(job.record.id)
    assert len(service.list_history()) == 1
    assert service.get_run(job.id).record is not None
    service.close()


def test_clear_history_storage_failure_leaves_records_and_current_run_intact():
    from molt_ui.repo.repo import RepoError

    repo = Repo()
    service = MoltService(MoltProcess(sys.executable), repo)
    original = service.import_log(StringIO("existing output\n"))
    with patch.object(repo, "clear_runs", side_effect=RepoError("database locked")):
        with pytest.raises(MoltError, match="database locked"):
            service.clear_history()
    assert len(service.list_history()) == 1
    assert service.get_run(original.id).record == original.record
    service.close()


def test_single_history_deletion_storage_failure_preserves_record():
    from molt_ui.repo.repo import RepoError

    repo = Repo()
    service = MoltService(MoltProcess(sys.executable), repo)
    original = service.import_log(StringIO("existing output\n"))
    with patch.object(repo, "delete_run", side_effect=RepoError("database locked")):
        with pytest.raises(MoltError, match="database locked"):
            service.delete_history_record(original.record.id)
    assert service.get_history_record(original.record.id) == original.record
    assert service.get_run(original.id).record == original.record
    service.close()
