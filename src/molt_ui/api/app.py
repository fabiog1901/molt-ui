import asyncio
import io
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import SpooledTemporaryFile

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from molt_ui.core import CliError, CliService, CommandResult, create_service

WEB_DIRECTORY = Path(__file__).resolve().parents[1] / "web"


class StartCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    options: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    help_only: bool = False


def create_app(service: CliService | None = None) -> FastAPI:
    service = service if service is not None else create_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await asyncio.to_thread(service.close)

    app = FastAPI(title="Molt UI", lifespan=lifespan)

    @app.get("/api/commands")
    def commands() -> list[dict]:
        return service.commands()

    @app.post("/api/jobs", status_code=201)
    def start_command(body: StartCommand) -> dict:
        try:
            return service.start(body.command, body.options, help_only=body.help_only).snapshot()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except CliError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/jobs")
    def latest_job() -> dict | None:
        job = service.jobs.latest()
        return job.snapshot() if job else None

    @app.post("/api/log-imports", status_code=201)
    async def import_log(request: Request) -> dict:
        # Raw file upload avoids multipart dependencies and browser-side buffering.
        with SpooledTemporaryFile(max_size=1024 * 1024) as upload:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 256 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Log uploads are limited to 256 MiB.")
                await asyncio.to_thread(upload.write, chunk)
            upload.seek(0)
            with io.TextIOWrapper(upload, encoding="utf-8-sig", errors="replace") as source:
                try:
                    job = await asyncio.to_thread(service.import_log, source)
                    return job.snapshot()
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                except CliError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc

    def get_job(job_id: str):
        try:
            return service.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found; only the latest run is retained.") from exc

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, after: int = Query(default=0, ge=0)) -> dict:
        return get_job(job_id).snapshot(after)

    @app.post("/api/jobs/{job_id}/stop")
    def stop_job(job_id: str) -> dict:
        job = get_job(job_id)
        job.stop()
        return job.snapshot()

    @app.get("/api/jobs/{job_id}/table-logs")
    def table_logs(job_id: str, table: str, limit: int = Query(default=50, ge=1, le=100)) -> dict:
        try:
            return get_job(job_id).table_logs(table, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Table not found in this run.") from exc

    @app.post("/api/cli/help", response_model=CommandResult)
    def cli_help() -> CommandResult:
        try:
            return service.help()
        except CliError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIRECTORY / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIRECTORY / "static"), name="static")
    return app


def main() -> None:
    uvicorn.run("molt_ui.api.app:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
