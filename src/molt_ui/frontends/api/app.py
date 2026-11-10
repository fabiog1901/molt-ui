import asyncio
import io
from contextlib import asynccontextmanager
from importlib.resources import files
from tempfile import SpooledTemporaryFile

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from molt_ui.bootstrap import create_service
from molt_ui.core.errors import MoltError
from molt_ui.core.models import (
    CommandPlan,
    CommandResult,
    RunRecord,
    RunSnapshot,
    TableLogs,
)
from molt_ui.core.service import MoltService
from molt_ui.frontends.models import CommandDefinition, StartCommand

WEBAPP_DIRECTORY = files("molt_ui.webapp")


def create_app(service: MoltService | None = None) -> FastAPI:
    service = service if service is not None else create_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await asyncio.to_thread(service.close)

    app = FastAPI(title="Molt UI", lifespan=lifespan)

    @app.exception_handler(MoltError)
    async def operation_error(request: Request, exc: MoltError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/api/commands", response_model_exclude_unset=True)
    def commands() -> list[CommandDefinition]:
        return [CommandDefinition.from_spec(item) for item in service.commands()]

    @app.post("/api/jobs", status_code=201)
    def start_command(body: StartCommand) -> RunSnapshot:
        try:
            return service.start(
                body.command,
                body.options,
                help_only=body.help_only,
                source_kind=body.source_kind,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/command-preview")
    def preview_command(body: StartCommand) -> CommandPlan:
        try:
            return service.preview(
                body.command,
                body.options,
                help_only=body.help_only,
                source_kind=body.source_kind,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/history")
    def run_history(limit: int = Query(default=50, ge=1, le=200)) -> list[RunRecord]:
        return service.list_history(limit)

    @app.get("/api/history/{record_id}")
    def history_record(record_id: str) -> RunRecord:
        try:
            return service.get_history_record(record_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Run record not found."
            ) from exc

    @app.get("/api/jobs")
    def latest_run() -> RunSnapshot | None:
        return service.latest_run()

    @app.post("/api/log-imports", status_code=201)
    async def import_log(request: Request) -> RunSnapshot:
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
            with io.TextIOWrapper(
                upload, encoding="utf-8-sig", errors="replace"
            ) as source:
                try:
                    return await asyncio.to_thread(service.import_log, source)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                except MoltError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/jobs/{run_id}")
    def run_status(run_id: str, after: int = Query(default=0, ge=0)) -> RunSnapshot:
        try:
            return service.get_run(run_id, after)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Run not found; only the latest run is retained.",
            ) from exc

    @app.post("/api/jobs/{run_id}/stop")
    def stop_run(run_id: str) -> RunSnapshot:
        try:
            return service.stop_run(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Run not found; only the latest run is retained.",
            ) from exc

    @app.get("/api/jobs/{run_id}/table-logs")
    def table_logs(
        run_id: str, table: str, limit: int = Query(default=50, ge=1, le=100)
    ) -> TableLogs:
        try:
            return service.get_table_logs(run_id, table, limit)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Run or table not found."
            ) from exc

    @app.post("/api/cli/help", response_model=CommandResult)
    def molt_help() -> CommandResult:
        return service.help()

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEBAPP_DIRECTORY / "index.html")

    app.mount(
        "/static", StaticFiles(directory=WEBAPP_DIRECTORY / "static"), name="static"
    )
    return app


def main() -> None:
    uvicorn.run(
        "molt_ui.frontends.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
