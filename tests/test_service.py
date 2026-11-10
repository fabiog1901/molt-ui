from io import StringIO
from pathlib import Path
import shlex
import sys
import time
from unittest.mock import patch

import pytest

from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandPlan
from molt_ui.core.service import MoltService
from molt_ui.molt_process import MoltProcess
from molt_ui.repo import Repo


def wait_for(service, run):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = service.get_run(run.id)
        if state.status != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("Run did not finish")


def test_exact_credentials_and_invocation_roundtrip_storage(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess("/path with spaces/molt"), Repo(path))
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


def test_completion_is_persisted_without_polling(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(path))
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


def test_preview_is_nonexecuting_and_prunes_invalid_options():
    service = MoltService(MoltProcess("molt"), Repo())
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
    assert set(plan.omitted) == {
        "bucket-path",
        "assume-role",
        "oracle-application-users",
    }
    assert "bucket-path" not in plan.options
    assert service.list_history() == []
    service.close()


def test_import_records_have_no_fabricated_command(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess("molt"), Repo(path))
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


def test_storage_failure_prevents_launch_and_failed_import_preserves_latest_run():
    from molt_ui.repo.repo import RepoError

    repo = Repo()
    service = MoltService(MoltProcess("molt"), repo)
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


def test_close_stops_the_live_run_and_persists_its_final_status(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(path))
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
