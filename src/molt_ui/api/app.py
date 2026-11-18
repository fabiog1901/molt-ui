import asyncio
import io
from contextlib import asynccontextmanager
from importlib.resources import files
from importlib.metadata import PackageNotFoundError, version
from tempfile import SpooledTemporaryFile
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from molt_ui.api.models import CommandDefinition, StartCommand
from molt_ui.bootstrap import create_service
from molt_ui.core.errors import MoltError, RunConflict
from molt_ui.core.models import (
    CommandPlan,
    CommandResult,
    HistoryOutput,
    RunRecord,
    RunSnapshot,
    TableLogs,
)
from molt_ui.core.service import MoltService
from molt_ui.file_picker import choose_file

WEBAPP_DIRECTORY = files("molt_ui.webapp")
try:
    APP_VERSION = version("molt-ui")
except PackageNotFoundError:
    APP_VERSION = "0+unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = await asyncio.to_thread(create_service)
    try:
        yield {"service": service}
    finally:
        await asyncio.to_thread(service.close)


def get_service(request: Request) -> MoltService:
    return request.state.service


Service = Annotated[MoltService, Depends(get_service)]
app = FastAPI(title="Molt UI", lifespan=lifespan)


@app.exception_handler(RunConflict)
async def run_conflict(request: Request, exc: RunConflict):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(MoltError)
async def operation_error(request: Request, exc: MoltError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/commands", response_model_exclude_unset=True)
def commands(service: Service) -> list[CommandDefinition]:
    return [CommandDefinition.from_spec(item) for item in service.commands()]


@app.post("/api/file-picker")
def pick_command_file() -> dict[str, str | None]:
    """Select an original file on the server's desktop without uploading a copy."""
    try:
        return {"path": choose_file()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/jobs", status_code=201)
def start_command(service: Service, body: StartCommand) -> RunSnapshot:
    try:
        return service.start(
            body.command,
            body.options,
            help_only=body.help_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/command-preview")
def preview_command(service: Service, body: StartCommand) -> CommandPlan:
    try:
        return service.preview(
            body.command,
            body.options,
            help_only=body.help_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/history")
def run_history(
    service: Service, limit: int = Query(default=50, ge=1, le=200)
) -> list[RunRecord]:
    return service.list_history(limit)


@app.delete("/api/history")
def clear_history(service: Service) -> dict[str, int]:
    return {"deleted": service.clear_history()}


@app.delete("/api/history/{record_id}")
def delete_history_record(service: Service, record_id: str) -> dict[str, int]:
    try:
        return {"deleted": service.delete_history_record(record_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run record not found.") from exc


@app.get("/api/history/{record_id}")
def history_record(service: Service, record_id: str) -> RunRecord:
    try:
        return service.get_history_record(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run record not found.") from exc


@app.get("/api/history/{record_id}/output")
def history_output(
    service: Service,
    record_id: str,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=2000, ge=1, le=2000),
) -> HistoryOutput:
    try:
        return service.get_history_output(record_id, before=before, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run record not found.") from exc


@app.get("/api/history/{record_id}/table-logs")
def history_table_logs(
    service: Service,
    record_id: str,
    table: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> TableLogs:
    try:
        return service.get_history_table_logs(record_id, table, limit)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="Run record or table not found."
        ) from exc


@app.post("/api/history/{record_id}/rerun", status_code=201)
def rerun_history_record(service: Service, record_id: str) -> RunSnapshot:
    try:
        return service.rerun(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run record not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/jobs")
def latest_run(service: Service) -> RunSnapshot | None:
    return service.latest_run()


@app.post("/api/log-imports", status_code=201)
async def import_log(service: Service, request: Request) -> RunSnapshot:
    with SpooledTemporaryFile(max_size=1024 * 1024) as upload:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 256 * 1024 * 1024:
                raise HTTPException(
                    status_code=413, detail="Log uploads are limited to 256 MiB."
                )
            await asyncio.to_thread(upload.write, chunk)
        upload.seek(0)
        with io.TextIOWrapper(upload, encoding="utf-8-sig", errors="replace") as source:
            try:
                filename = request.headers.get("X-Log-Filename")
                return await asyncio.to_thread(
                    service.import_log,
                    source,
                    filename=unquote(filename) if filename else None,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except MoltError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/jobs/{run_id}")
def run_status(
    service: Service, run_id: str, after: int = Query(default=0, ge=0)
) -> RunSnapshot:
    try:
        return service.get_run(run_id, after)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Run not found; only the latest run is retained.",
        ) from exc


@app.post("/api/jobs/{run_id}/stop")
def stop_run(service: Service, run_id: str) -> RunSnapshot:
    try:
        return service.stop_run(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Run not found; only the latest run is retained.",
        ) from exc


@app.get("/api/jobs/{run_id}/table-logs")
def table_logs(
    service: Service,
    run_id: str,
    table: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> TableLogs:
    try:
        return service.get_table_logs(run_id, table, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run or table not found.") from exc


@app.post("/api/cli/help", response_model=CommandResult)
def molt_help(service: Service) -> CommandResult:
    return service.help()


@app.get("/api/jobs/{run_id}/metrics")
def run_metrics(
    service: Service,
    run_id: str,
    after: float = Query(default=0, ge=0, allow_inf_nan=False),
) -> dict:
    try:
        return service.get_run_metrics(run_id, after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@app.get("/api/history/{record_id}/metrics")
def history_metrics(
    service: Service,
    record_id: str,
    after: float = Query(default=0, ge=0, allow_inf_nan=False),
) -> dict:
    try:
        return service.get_history_metrics(record_id, after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run record not found.") from exc


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse(
        (WEBAPP_DIRECTORY / "index.html").read_text().replace("__APP_VERSION__", APP_VERSION)
    )


app.mount("/static", StaticFiles(directory=WEBAPP_DIRECTORY / "static"), name="static")
