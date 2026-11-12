from unittest.mock import Mock

from fastapi.testclient import TestClient

from molt_ui.frontends.api.app import create_app
from molt_ui.core.errors import MoltError
from molt_ui.core.models import CommandPlan, CommandResult, LogEntry
from molt_ui.core.service import MoltService
from molt_ui.molt_process import MoltProcess
from molt_ui.repo import Repo


def test_api_uses_the_shared_service():
    service = Mock(spec=MoltService)
    service.help.return_value = CommandResult(
        stdout="output",
        stderr="warning",
        returncode=1,
        logs=(LogEntry(stream="stderr", data={"level": "warn"}),),
    )
    with TestClient(create_app(service)) as client:
        response = client.post("/api/cli/help")
        assert response.status_code == 200
        assert response.json() == {
            "stdout": "output",
            "stderr": "warning",
            "returncode": 1,
            "logs": [{"stream": "stderr", "data": {"level": "warn"}}],
        }
    service.help.assert_called_once_with()


def test_cli_failure_is_returned_to_the_ui():
    service = Mock(spec=MoltService)
    service.help.side_effect = MoltError("Executable missing")
    with TestClient(create_app(service)) as client:
        response = client.post("/api/cli/help")
        assert response.status_code == 503
        assert response.json()["detail"] == "Executable missing"


def test_frontend_assets_are_served(command_catalog):
    with TestClient(create_app(MoltService(MoltProcess("/unused"), Repo(), catalog=command_catalog))) as client:
        assert 'x-data="cliApp"' in client.get("/").text
        for path in ("/static/styles.css", "/static/app.js"):
            assert client.get(path).status_code == 200
        assert client.get("/api/unknown").status_code == 404


def test_job_api_runs_real_help_and_reports_validation_errors(command_catalog):
    import sys
    import time

    service = MoltService(MoltProcess(sys.executable), Repo(), catalog=command_catalog)
    with TestClient(create_app(service)) as client:
        commands = client.get("/api/commands").json()
        assert any(command["id"] == "fetch" for command in commands)
        assert client.post("/api/jobs", json={"command": "invalid"}).status_code == 422
        assert (
            client.post(
                "/api/jobs", json={"command": "fetch", "options": {"direct-copy": 123}}
            ).status_code
            == 422
        )
        # Python rejects the fetch argument; still tests the real process lifecycle.
        response = client.post(
            "/api/jobs", json={"command": "fetch", "help_only": True}
        )
        assert response.status_code == 201
        job_id = response.json()["id"]
        for _ in range(100):
            snapshot = client.get(f"/api/jobs/{job_id}").json()
            if snapshot["status"] != "running":
                break
            time.sleep(0.01)
        assert snapshot["status"] == "failed"
        assert snapshot["returncode"] != 0
        assert "Molt exited with code" in snapshot["error"]
        assert snapshot["record"]["error"] == snapshot["error"]
        assert (
            client.get(f'/api/jobs/{job_id}?after={snapshot["cursor"]}').json()[
                "events"
            ]
            == []
        )
        assert client.post(f"/api/jobs/{job_id}/stop").status_code == 200
        assert client.get("/api/jobs/missing").status_code == 404


def test_aggregate_snapshot_and_lazy_table_logs_are_consistent(command_catalog):
    import sys
    import time

    service = MoltService(MoltProcess(sys.executable), Repo(), catalog=command_catalog)
    with TestClient(create_app(service)) as client:
        code = """import json
print(json.dumps({'level': 'info', 'source_table': 'public.actor', 'target_table': 'public.actor', 'message': 'found matching table'}))
print(json.dumps({'level': 'info', 'table': 'public.actor', 'num_rows': 200, 'message': 'data extraction from source complete'}))
print(json.dumps({'level': 'warn', 'message': 'global warning'}))
"""
        from unittest.mock import patch

        plan = CommandPlan(
            command="fetch",
            argv=(sys.executable, "-c", code),
            environment={},
            options={},
            invocation="python test",
        )
        with patch.object(service, "preview", return_value=plan):
            job = service.start("fetch", {})
        for _ in range(100):
            snapshot = client.get(f"/api/jobs/{job.id}").json()
            if snapshot["status"] != "running":
                break
            time.sleep(0.01)
        assert snapshot["aggregation"]["totals"]["exported"] == 200
        assert snapshot["aggregation"]["totals"]["warnings"] == 1
        repeated = client.get(f'/api/jobs/{job.id}?after={snapshot["cursor"]}').json()
        assert repeated["events"] == []
        assert repeated["aggregation"] == snapshot["aggregation"]
        details = client.get(
            f"/api/jobs/{job.id}/table-logs",
            params={"table": "public.actor", "limit": 1},
        ).json()
        assert details["total"] == 2
        assert details["truncated"] is True
        assert len(details["events"]) == 1
        assert details["events"][0]["data"]["num_rows"] == 200
        assert (
            client.get(
                f"/api/jobs/{job.id}/table-logs", params={"table": "unknown"}
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/jobs/{job.id}/table-logs",
                params={"table": "public.actor", "limit": 101},
            ).status_code
            == 422
        )


def test_upload_imports_jsonl_and_preserves_a_previous_preview_on_empty_upload(command_catalog):
    from pathlib import Path

    with TestClient(create_app(MoltService(MoltProcess("/unused"), Repo(), catalog=command_catalog))) as client:
        sample = (
            Path(__file__).parents[1] / "src/molt_ui/webapp/static/sample-fetch.jsonl"
        )
        response = client.post(
            "/api/log-imports",
            content=b"\xef\xbb\xbf" + sample.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 201
        preview = response.json()
        assert preview["status"] == "imported"
        assert preview["returncode"] is None
        assert preview["aggregation"]["totals"]["exported"] == 63307
        assert preview["aggregation"]["totals"]["warnings"] == 19
        assert client.get("/api/jobs").json()["id"] == preview["id"]
        assert (
            client.get(
                f'/api/jobs/{preview["id"]}/table-logs',
                params={"table": "public.actor"},
            ).status_code
            == 200
        )
        assert client.post("/api/log-imports", content=b"").status_code == 422
        assert client.get("/api/jobs").json()["id"] == preview["id"]
        assert client.get("/static/sample-fetch.jsonl").status_code == 200


def test_wizard_preview_is_nonexecuting_and_history_survives_a_new_app(command_catalog, tmp_path):
    import sys
    import time
    from unittest.mock import patch

    database = str(tmp_path / "metadata.sqlite3")
    service = MoltService(MoltProcess(sys.executable), Repo(database), catalog=command_catalog)
    with TestClient(create_app(service)) as client:
        with patch("molt_ui.molt_process.subprocess.Popen") as spawn:
            response = client.post(
                "/api/command-preview",
                json={
                    "command": "fetch",
                    "options": {
                        "source": "postgres://user:secret@source/db",
                        "target": "postgres://target/db",
                        "direct-copy": True,
                        "bucket-path": "s3://bucket",
                    },
                },
            )
            assert response.status_code == 200
            assert response.json()["omitted"] == []
            assert "--bucket-path=s3://bucket" in response.json()["argv"]
            assert "user:secret@source" in response.json()["invocation"]
            assert client.get("/api/history").json() == []
            spawn.assert_not_called()
        response = client.post(
            "/api/jobs", json={"command": "fetch", "help_only": True}
        )
        assert response.status_code == 201
        job_id = response.json()["id"]
        for _ in range(100):
            state = client.get(f"/api/jobs/{job_id}").json()
            if state["status"] != "running":
                break
            time.sleep(0.01)
        record_id = state["record"]["id"]
        assert state["record"]["invocation"].endswith("fetch --help")
    restarted = MoltService(MoltProcess("molt"), Repo(database), catalog=command_catalog)
    with TestClient(create_app(restarted)) as client:
        records = client.get("/api/history").json()
        assert records[0]["id"] == record_id
        assert records[0]["status"] == "failed"
        assert records[0]["returncode"] != 0
        assert records[0]["finished_at"]
        assert client.get(f"/api/history/{record_id}").json() == records[0]
        assert client.get("/api/history/unknown").status_code == 404


def test_source_picker_is_frontend_context_and_does_not_change_execution_plan(command_catalog):
    with TestClient(create_app(MoltService(MoltProcess("/unused"), Repo(), catalog=command_catalog))) as client:
        response = client.post(
            "/api/command-preview",
            json={
                "command": "fetch",
                "source_kind": "oracle",
                "options": {
                    "source": "user=app password=example",
                    "target": "postgres://target/db",
                    "oracle-application-users": "app",
                    "pglogical-replication-slot-name": "not-for-oracle",
                },
            },
        )
        assert response.status_code == 200
        preview = response.json()
        assert preview["omitted"] == []
        assert "--pglogical-replication-slot-name=not-for-oracle" in preview["argv"]
        assert "--oracle-application-users=app" in preview["argv"]
        assert not any("source_kind" in argument for argument in preview["argv"])
        assert (
            client.post(
                "/api/command-preview",
                json={
                    "command": "fetch",
                    "source_kind": "oracle",
                    "options": {
                        "source": "mysql://source/db",
                        "target": "postgres://target/db",
                    },
                },
            ).status_code
            == 200
        )


def test_incompatible_modal_catalog_is_reported_as_an_actionable_error(command_catalog):

    service = Mock(spec=MoltService)
    fetch = next(spec for spec in command_catalog.commands if spec.id == "fetch")
    service.commands.return_value = (fetch.model_copy(update={
        "options": tuple(option for option in fetch.options if option.name != "source"),
    }),)
    with TestClient(create_app(service)) as client:
        response = client.get("/api/commands")
        assert response.status_code == 503
        assert "no longer contains --source" in response.json()["detail"]
        assert client.get("/").status_code == 200


def test_history_rerun_endpoint_starts_a_new_job_and_retains_the_original():
    import sys
    import time

    repo = Repo()
    original = repo.create_run("fetch", origin="help", argv=("/old/molt", "--help"),
                               invocation="/old/molt --help")
    original = repo.update_run(original.id, status="succeeded", returncode=0)
    imported = repo.create_run("fetch", origin="import")
    service = MoltService(MoltProcess(sys.executable), repo)
    with TestClient(create_app(service)) as client:
        assert client.post("/api/history/missing/rerun").status_code == 404
        assert client.post(f"/api/history/{imported.id}/rerun").status_code == 422
        response = client.post(f"/api/history/{original.id}/rerun")
        assert response.status_code == 201
        state = response.json()
        for _ in range(100):
            state = client.get(f"/api/jobs/{state['id']}").json()
            if state["status"] != "running":
                break
            time.sleep(.01)
        assert state["status"] == "succeeded"
        assert state["record"]["id"] != original.id
        assert state["record"]["origin"] == "help"
        assert state["record"]["argv"] == [sys.executable, "--help"]
        assert client.get(f"/api/history/{original.id}").json() == original.model_dump(mode="json")
        assert len(client.get("/api/history").json()) == 3


def test_clear_history_endpoint_deletes_records_and_preserves_current_output(command_catalog):
    from io import StringIO

    repo = Repo()
    catalog = repo.save_catalog("v1", command_catalog)
    service = MoltService(MoltProcess("/unused"), repo, catalog=command_catalog)
    original = service.import_log(StringIO("saved output\n"))
    with TestClient(create_app(service)) as client:
        response = client.delete("/api/history")
        assert response.status_code == 200
        assert response.json() == {"deleted": 1}
        assert client.get("/api/history").json() == []
        assert client.get(f"/api/history/{original.record.id}").status_code == 404
        current = client.get(f"/api/jobs/{original.id}").json()
        assert current["events"][0]["text"] == "saved output"
        assert current["record"] is None
        assert repo.get_catalog() == catalog
        assert client.delete("/api/history").json() == {"deleted": 0}


def test_delete_single_history_record_cascades_output_and_preserves_other_records(command_catalog, tmp_path):
    from io import StringIO

    repo = Repo(str(tmp_path / "history.sqlite3"))
    catalog = repo.save_catalog("v1", command_catalog)
    service = MoltService(MoltProcess("/unused"), repo, catalog=command_catalog)
    first = service.import_log(StringIO("first saved output\n"))
    second = service.import_log(StringIO("second saved output\n"))
    logfile = tmp_path / "saved.log"
    logfile.write_text("keep this log file\n")
    repo.update_run(second.record.id, status="imported", log_file=str(logfile))
    with TestClient(create_app(service)) as client:
        assert client.delete(f"/api/history/{first.record.id}").json() == {"deleted": 1}
        assert client.get(f"/api/history/{first.record.id}").status_code == 404
        assert client.get(f"/api/history/{first.record.id}/output").status_code == 404
        assert repo._connection.execute("SELECT COUNT(*) FROM run_output WHERE run_id=?", (first.record.id,)).fetchone()[0] == 0
        assert client.get(f"/api/jobs/{second.id}").json()["record"]["id"] == second.record.id
        assert [record["id"] for record in client.get("/api/history").json()] == [second.record.id]
        assert client.delete(f"/api/history/{second.record.id}").json() == {"deleted": 1}
        assert client.get(f"/api/jobs/{second.id}").json()["record"] is None
        assert client.delete(f"/api/history/{second.record.id}").status_code == 404
        assert client.get("/api/history").json() == []
        assert logfile.read_text() == "keep this log file\n"
        assert repo.get_catalog() == catalog
