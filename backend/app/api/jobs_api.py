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
from app.api.routes import Rule, _error_response
from app.jobs import planning
from app.jobs.manager import JobManager, public
from app.settings import DEFAULT_TEMPLATE
from app.ytdlp import naming, offers

router = APIRouter(prefix="/api")

Mode = Literal["mkv", "compat_mp4", "separate", "audio"]
AudioCodec = Literal["mp3", "m4a", "opus", "flac", "wav"]
SSE_KEEPALIVE_SECONDS = 5


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


class QuickRequest(BaseModel):
    """One click: a quick choice of an inspected video, or a URL plus a remembered rule."""

    inspect_id: str | None = Field(default=None, min_length=1, max_length=64)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    offer_id: str | None = Field(default=None, min_length=1, max_length=64)
    output: Literal["mkv", "compat_mp4"] | None = None
    rule: Rule | None = None
    audio_language: str | None = Field(default=None, max_length=64)
    subtitle_keys: list[str] | None = Field(default=None, max_length=400)


class SettingsBody(BaseModel):
    download_dir: str = Field(min_length=1, max_length=1024)
    filename_template: str = Field(min_length=1, max_length=500)
    concurrency: int = Field(ge=1, le=6)
    default_mode: Mode
    clipboard_watch: bool = False
    safari_login: bool = True
    notifications: bool = True
    extension_offer: Literal["page", "icon"] = "page"
    accelerate: bool = True
    connections: int = Field(default=8, ge=1, le=16)
    rate_limit: int = Field(default=0, ge=0, le=10_000_000_000)
    auto_update_ytdlp: bool = True


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


@router.post("/quick")
async def post_quick(body: QuickRequest, request: Request) -> Any:
    """Queue a download from a quick choice. Answers with the job and what was chosen, so the
    caller can remember the choice as a rule for the next video."""
    manager = _manager(request)
    settings = settings_store.load()
    try:
        if body.inspect_id:
            entry = inspect_service.recall(body.inspect_id)
        elif body.url:
            try:
                model = await inspect_service.inspect(body.url, reuse=True)
            except errors.AppError as exc:
                return _error_response(exc)  # extraction failures answer as /api/inspect does
            if "inspect_id" not in model:
                raise errors.AppError(code="QUICK_NEEDS_VIDEO", raw=body.url)
            entry = inspect_service.recall(model["inspect_id"])
        else:
            raise errors.AppError(code="QUICK_NEEDS_SOURCE")
        model = entry["model"]
        choices = model.get("offers") or offers.build(model)
        if body.offer_id:
            offer_id, output = body.offer_id, body.output
        else:
            rule = body.rule.model_dump() if body.rule else None
            if rule is not None and body.output:
                rule["output"] = body.output  # an explicit output wins over the remembered one
            picked = offers.match(choices, rule, settings.default_mode)
            if picked is None:
                raise errors.AppError(code="QUICK_NOTHING_OFFERED", raw=model["source_url"])
            offer_id, output = picked["offer_id"], picked["output"] or body.output
        rows = {r["id"]: r for r in [*choices["video"], *choices["audio"]]}
        if offer_id not in rows:
            raise errors.AppError(code="OFFER_UNKNOWN", raw=offer_id)
        chosen = offers.resolve(
            model,
            offer_id,
            output,
            body.audio_language,
            body.subtitle_keys,
            default_mode=settings.default_mode,
        )
        selection = Selection(inspect_id=model["inspect_id"], **chosen).model_dump()
        job = manager.store.insert(planning.build_job(entry, selection, settings))
    except errors.AppError as exc:
        return _error(exc, 410 if exc.code == "INSPECT_EXPIRED" else 400)
    manager.publish({"type": "job", "job": public(job)})
    manager.wake()
    return {
        "job": public(job),
        "offer_id": offer_id,
        "output": chosen["mode"] if chosen["mode"] != "audio" else None,
        "rule": offers.rule_for(rows[offer_id], chosen["mode"]),
        "selection": {k: v for k, v in selection.items() if k != "extras"},
    }


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


@router.post("/jobs/{job_id}/pause")
async def post_pause(job_id: str, request: Request) -> Any:
    return _job_or_404(_manager(request).pause(job_id))


@router.post("/jobs/{job_id}/resume")
async def post_resume(job_id: str, request: Request) -> Any:
    return _job_or_404(_manager(request).resume(job_id))


@router.post("/jobs/pause-all")
async def post_pause_all(request: Request) -> dict[str, int]:
    return {"paused": _manager(request).pause_all()}


@router.post("/jobs/resume-all")
async def post_resume_all(request: Request) -> dict[str, int]:
    return {"resumed": _manager(request).resume_all()}


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
    return {**settings_store.load().as_dict(), "default_filename_template": DEFAULT_TEMPLATE}


@router.put("/settings")
async def put_settings(body: SettingsBody, request: Request) -> Any:
    try:
        naming.validate_template(body.filename_template)
    except errors.AppError as exc:
        return _error(exc)
    try:
        directory = settings_store.validate_download_dir(body.download_dir)
    except errors.AppError as exc:
        return _error(exc)
    saved = settings_store.save(
        settings_store.Settings(**{**body.model_dump(), "download_dir": str(directory)})
    )
    _manager(request).wake()  # a higher concurrency limit takes effect immediately
    return saved.as_dict()


@router.post("/jobs/{job_id}/reveal")
async def post_reveal(job_id: str, body: RevealBody, request: Request) -> Any:
    """Select one of a job's output files in Finder -- checked against *that job's* folder, so
    it keeps working after the download folder setting changes, and reveals nothing else."""
    job = _manager(request).store.get(job_id)
    files = (job or {}).get("output_files") or []
    if job is None or body.index >= len(files):
        return _error(errors.AppError(code="JOB_NOT_FOUND"), 404)
    # A download's root is its download folder; a Studio job writes next to its source.
    req = job["request"]
    root = Path(req.get("output_dir") or req["download_dir"])
    try:
        return {"shown": notify.reveal(files[body.index], root)}
    except errors.AppError as exc:
        return _error(exc, 409)
