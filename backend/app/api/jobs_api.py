"""Download planning, the job queue, live events, settings, notifications."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import errors, inspect_service, notify
from app import settings as settings_store
from app.jobs import planning
from app.jobs.manager import JobManager, public
from app.ytdlp import naming

router = APIRouter(prefix="/api")

Mode = Literal["mkv", "compat_mp4", "separate", "audio"]
AudioCodec = Literal["mp3", "m4a", "opus", "flac", "wav"]
SSE_KEEPALIVE_SECONDS = 5
# Downloads create folders and the library reveals files under this root; never the disk itself.
UNSAFE_DOWNLOAD_DIRS = {
    Path(p).resolve()
    for p in (
        "/",
        "/System",
        "/Library",
        "/Applications",
        "/usr",
        "/bin",
        "/etc",
        "/private",
        "/Users",
    )
}


class Extras(BaseModel):
    thumbnail: bool = True  # embed as cover art / MKV attachment
    thumbnail_file: bool = False
    description: bool = False
    info_json: bool = False


class Selection(BaseModel):
    inspect_id: str = Field(min_length=1, max_length=64)
    mode: Mode
    video_format_id: str | None = Field(default=None, max_length=64)
    audio_format_ids: list[str] = Field(default_factory=list, max_length=64)
    subtitle_keys: list[str] = Field(default_factory=list, max_length=400)
    audio_codec: AudioCodec | None = None
    audio_quality: str | None = Field(default=None, pattern=r"^\d{1,3}$")
    filename_template: str | None = Field(default=None, max_length=500)
    extras: Extras = Field(default_factory=Extras)


class SettingsBody(BaseModel):
    download_dir: str = Field(min_length=1, max_length=1024)
    filename_template: str = Field(min_length=1, max_length=500)
    concurrency: int = Field(ge=1, le=6)
    default_mode: Mode
    clipboard_watch: bool = False
    notifications: bool = True


class NotifyBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=500)


class RevealBody(BaseModel):
    index: int = Field(ge=0, lt=1000)


def _manager(request: Request) -> JobManager:
    manager: JobManager = request.app.state.jobs
    return manager


def _error(exc: errors.AppError, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


@router.post("/plan")
def post_plan(selection: Selection) -> Any:
    try:
        entry = inspect_service.recall(selection.inspect_id)
        return planning.plan(entry, selection.model_dump(), settings_store.load())
    except errors.AppError as exc:
        return _error(exc, 410 if exc.code == "INSPECT_EXPIRED" else 400)


@router.get("/jobs")
async def get_jobs(request: Request) -> list[dict[str, Any]]:
    return [public(job) for job in _manager(request).store.all()]


@router.post("/jobs")
async def post_job(selection: Selection, request: Request) -> Any:
    manager = _manager(request)
    try:
        entry = inspect_service.recall(selection.inspect_id)
        job = manager.store.insert(
            planning.build_job(entry, selection.model_dump(), settings_store.load())
        )
    except errors.AppError as exc:
        return _error(exc, 410 if exc.code == "INSPECT_EXPIRED" else 400)
    manager.publish({"type": "job", "job": public(job)})
    manager.wake()
    return public(job)


def _job_or_404(job: dict[str, Any] | None) -> Any:
    if job is None:
        return _error(errors.AppError(code="JOB_NOT_FOUND"), 404)
    return public(job)


@router.post("/jobs/{job_id}/cancel")
async def post_cancel(job_id: str, request: Request) -> Any:
    return _job_or_404(_manager(request).cancel(job_id))


@router.post("/jobs/{job_id}/retry")
async def post_retry(job_id: str, request: Request) -> Any:
    return _job_or_404(_manager(request).retry(job_id))


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request) -> Any:
    if not _manager(request).remove(job_id):
        return _error(errors.AppError(code="JOB_NOT_REMOVABLE"), 409)
    return {"ok": True}


@router.get("/events")
async def get_events(request: Request) -> StreamingResponse:
    manager = _manager(request)
    queue = manager.subscribe()

    async def stream() -> AsyncIterator[str]:
        try:
            snapshot = [public(job) for job in manager.store.all()]
            yield "retry: 2000\n\n"
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), SSE_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if payload["type"] == "shutdown":
                    break  # let the server stop without waiting on open streams
                yield f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n"
        finally:
            manager.unsubscribe(queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return settings_store.load().as_dict()


@router.put("/settings")
async def put_settings(body: SettingsBody, request: Request) -> Any:
    try:
        naming.validate_template(body.filename_template)
    except errors.AppError as exc:
        return _error(exc)
    directory = Path(body.download_dir).expanduser()
    if not directory.is_absolute():
        return _error(errors.AppError(code="DOWNLOAD_DIR_NOT_ABSOLUTE", raw=body.download_dir))
    if directory.resolve() in UNSAFE_DOWNLOAD_DIRS:
        return _error(errors.AppError(code="DOWNLOAD_DIR_UNSAFE", raw=body.download_dir))
    saved = settings_store.save(
        settings_store.Settings(**{**body.model_dump(), "download_dir": str(directory)})
    )
    _manager(request).wake()  # a higher concurrency limit takes effect immediately
    return saved.as_dict()


@router.post("/notify")
def post_notify(body: NotifyBody) -> dict[str, bool]:
    return {"shown": notify.notify(body.title, body.body)}


@router.post("/jobs/{job_id}/reveal")
async def post_reveal(job_id: str, body: RevealBody, request: Request) -> Any:
    """Select one of a job's output files in Finder -- checked against *that job's* folder, so
    it keeps working after the download folder setting changes, and reveals nothing else."""
    job = _manager(request).store.get(job_id)
    files = (job or {}).get("output_files") or []
    if job is None or body.index >= len(files):
        return _error(errors.AppError(code="JOB_NOT_FOUND"), 404)
    root = Path(job["request"]["download_dir"])
    try:
        return {"shown": notify.reveal(files[body.index], root)}
    except errors.AppError as exc:
        return _error(exc, 409)
