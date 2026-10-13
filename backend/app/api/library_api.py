"""Library, system actions (folder picker, yt-dlp update) and the settings preview."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app import errors, paths, system
from app import settings as settings_store
from app.library import Library
from app.ytdlp import naming

router = APIRouter(prefix="/api")


class PickFolderBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=200)


class TemplatePreviewBody(BaseModel):
    template: str = Field(min_length=1, max_length=500)
    sample: dict[str, str | int | None] = Field(default_factory=dict)
    ext: str = Field(default="mkv", pattern=r"^[a-z0-9]{1,5}$")


def _library(request: Request) -> Library:
    library: Library = request.app.state.library
    return library


def _error(exc: errors.AppError, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


@router.get("/library")
def get_library(
    request: Request,
    search: str = "",
    site: str | None = None,
    kind: Literal["video", "audio"] | None = None,
    status: Literal["ok", "missing"] | None = None,
    sort: Literal["added", "title", "size", "duration", "uploaded"] = "added",
) -> dict[str, Any]:
    library = _library(request)
    return {
        "items": library.query(search=search[:200], site=site, kind=kind, status=status, sort=sort),
        "facets": library.facets(),
    }


@router.post("/library/scan")
async def post_scan(request: Request) -> Any:
    root = Path(settings_store.load().download_dir).expanduser()
    try:
        # ffprobe and Spotlight can take a moment; keep the event loop free.
        return await asyncio.to_thread(_library(request).scan, [root])
    except errors.AppError as exc:
        return _error(exc, 409)


@router.get("/library/{item_id}/thumbnail", response_model=None)
def get_thumbnail(item_id: str, request: Request) -> FileResponse | JSONResponse:
    path = _library(request).thumbnail(item_id)
    if path is None:
        return JSONResponse(status_code=404, content={"error": {"code": "NO_THUMBNAIL"}})
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


def _open(argv: list[str]) -> bool:
    if paths.fixture_mode() or sys.platform != "darwin":
        return False
    subprocess.run(argv, capture_output=True, timeout=10, check=False)
    return True


@router.post("/library/{item_id}/reveal")
def post_reveal_item(item_id: str, request: Request) -> Any:
    try:
        path = _library(request).existing_primary(item_id)
    except errors.AppError as exc:
        return _error(exc, 404 if exc.code == "ITEM_NOT_FOUND" else 409)
    return {"shown": _open(["open", "-R", str(path)])}


@router.post("/library/{item_id}/open")
def post_open_item(item_id: str, request: Request) -> Any:
    """Play in the default app (IINA, QuickTime, …). There is deliberately no in-app player."""
    try:
        path = _library(request).existing_primary(item_id)
    except errors.AppError as exc:
        return _error(exc, 404 if exc.code == "ITEM_NOT_FOUND" else 409)
    return {"opened": _open(["open", str(path)])}


@router.post("/library/{item_id}/trash")
def post_trash_item(item_id: str, request: Request) -> Any:
    """Move to the macOS Trash (recoverable). The UI asks for confirmation first."""
    try:
        return _library(request).trash(item_id)
    except errors.AppError as exc:
        status = {"ITEM_NOT_FOUND": 404, "TRASH_FAILED": 500}.get(exc.code, 409)
        return _error(exc, status)


@router.post("/system/pick-folder")
async def post_pick_folder(body: PickFolderBody) -> Any:
    try:
        return {"path": await asyncio.to_thread(system.pick_folder, body.prompt)}
    except errors.AppError as exc:
        return _error(exc, 501)


@router.post("/system/open-full-disk-access")
async def post_open_full_disk_access() -> Any:
    try:
        await asyncio.to_thread(system.open_full_disk_access)
    except errors.AppError as exc:
        return _error(exc, 501)
    return {"ok": True}


@router.post("/system/update-ytdlp")
async def post_update_ytdlp(request: Request) -> Any:
    # `uv sync` swaps yt-dlp's files; a running worker importing an extractor lazily would break.
    if request.app.state.jobs.active:
        return _error(errors.AppError(code="JOBS_RUNNING"), 409)
    try:
        return await asyncio.to_thread(system.update_ytdlp)
    except errors.AppError as exc:
        return _error(exc, 501 if exc.code == "UPDATE_UNAVAILABLE" else 500)


@router.post("/settings/preview-template")
def post_preview_template(body: TemplatePreviewBody) -> Any:
    """Render a template against sample values the UI provides (its text lives in tr.ts)."""
    try:
        relative = naming.render_relative(body.template, dict(body.sample), body.ext)
    except errors.AppError as exc:
        return _error(exc)
    return {"filename": f"{relative}.{body.ext}"}
