from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import doctor, errors, inspect_service, paths
from app.ytdlp import command

router = APIRouter(prefix="/api")


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class CommandRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    video_format_id: str | None = None
    audio_format_ids: list[str] = Field(default_factory=list)
    subtitle_keys: list[str] = Field(default_factory=list)
    mode: str = command.MODE_MKV


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
        return await inspect_service.inspect(request.url)
    except errors.AppError as exc:
        return _error_response(exc)


@router.post("/command")
def post_command(request: CommandRequest) -> dict[str, Any]:
    argv = command.build_command(
        request.url,
        video_format_id=request.video_format_id,
        audio_format_ids=request.audio_format_ids,
        subtitle_keys=request.subtitle_keys,
        mode=request.mode,
    )
    return {"argv": argv, "text": command.quote(argv)}
