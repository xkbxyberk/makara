from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import doctor, errors, inspect_service, paths
from app import settings as settings_store
from app.ytdlp import offers, support

router = APIRouter(prefix="/api")


class Rule(BaseModel):
    """The remembered shape of a quick choice ("1080p, MKV"), carried over to the next video."""

    kind: Literal["video", "audio"]
    height: int | None = Field(default=None, ge=1, le=10_000)
    fps: float | None = Field(default=None, ge=0, le=1000)
    hdr: bool = False
    output: Literal["mkv", "compat_mp4"] | None = None
    format: Literal["opus", "m4a", "mp3"] | None = None


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    # The Safari popup reuses a recent inspection of the same page; the İncele button does not.
    reuse: bool = False
    rule: Rule | None = None


def with_preselection(model: dict[str, Any], rule: Rule | None) -> dict[str, Any]:
    """The model plus which quick choice to preselect. The cached model is never mutated."""
    if "offers" not in model:
        return model
    preselected = offers.match(
        model["offers"],
        rule.model_dump() if rule else None,
        settings_store.load().default_mode,
    )
    return {**model, "offers": {**model["offers"], "preselected": preselected}}


def _error_response(exc: errors.AppError) -> JSONResponse:
    status = 400 if exc.code in ("INVALID_URL", "UNSUPPORTED_SITE") else 502
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


@router.get("/doctor")
def get_doctor() -> dict[str, Any]:
    return doctor.run_doctor()


@router.get("/health")
def get_health() -> dict[str, Any]:
    return {"ok": True, "fixture_mode": paths.fixture_mode()}


@router.post("/inspect")
async def post_inspect(request: InspectRequest) -> Any:
    try:
        model = await inspect_service.inspect(request.url, reuse=request.reuse)
    except errors.AppError as exc:
        return _error_response(exc)
    return with_preselection(model, request.rule)


@router.get("/supports")
def get_supports(url: str = Query(min_length=1, max_length=2048)) -> dict[str, Any]:
    """Offline: does yt-dlp have an extractor for this page (the generic one aside)?"""
    return support.supports(url)
