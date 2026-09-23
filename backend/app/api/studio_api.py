"""Studio: probe a source, preview the exact FFmpeg plan, and queue it."""

from __future__ import annotations

import asyncio
import shlex
import sys
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import errors, paths
from app import settings as settings_store
from app.jobs.manager import JobManager, public
from app.library import Library
from app.studio import ops
from app.ytdlp import naming

router = APIRouter(prefix="/api")

Operation = Literal["audio", "trim", "remux", "subtitle"]


class ProbeBody(BaseModel):
    path: str | None = Field(default=None, max_length=4096)
    item_id: str | None = Field(default=None, max_length=64)


class StudioBody(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    op: Operation
    options: dict[str, Any] = Field(default_factory=dict)
    output_name: str = Field(min_length=1, max_length=400)
    output_dir: str | None = Field(default=None, max_length=4096)
    extra_paths: list[str] = Field(default_factory=list, max_length=16)


class PickFileBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=200)


def _error(exc: errors.AppError, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


def _output_dir(body: StudioBody, source: Path) -> Path:
    """Next to the source by default, or the download folder -- never anywhere else."""
    allowed = {
        source.parent.resolve(),
        Path(settings_store.load().download_dir).expanduser().resolve(),
    }
    chosen = (
        Path(body.output_dir).expanduser().resolve() if body.output_dir else source.parent.resolve()
    )
    if chosen not in allowed:
        raise errors.AppError(code="OUTPUT_DIR_NOT_ALLOWED", raw=str(chosen))
    return chosen


def _prepare(body: StudioBody) -> tuple[dict[str, Any], Path, ops.Plan, list[str]]:
    """Build exactly the plan the worker will run: same encoder choice, the output name that
    claim() will pick right now, and a neutral stand-in for the job's scratch folder."""
    from app.workers.download_worker import _aac_encoder

    source_path = Path(body.source_path).expanduser()
    source = ops.probe_source(source_path)
    extras = [ops.probe_source(Path(p).expanduser()) for p in body.extra_paths]
    out_dir = _output_dir(body, source_path)
    ext = ops.output_ext(body.op, source, body.options)
    keyframes: dict[float, float | None] = {}
    if body.op == "trim" and (body.options.get("mode") or "lossless") == "lossless":
        for seg in body.options.get("segments") or []:
            start = ops._number(seg, "start", 0.0) or 0.0
            keyframes[start] = ops.keyframe_at_or_before(source_path, start)
    count = ops.separate_outputs(body.op, body.options)
    suffixes = [f".{n + 1}.{ext}" for n in range(count)] if count > 1 else [f".{ext}"]
    names = [
        str(p) for p in naming.first_free(out_dir, naming.safe_filename(body.output_name), suffixes)
    ]
    base = names[0][: -len(naming.safe_suffix(suffixes[0]))]
    template = f"{base}.{{N}}.{ext}" if count > 1 else names[0]
    scratch = f"{out_dir}/.vd-work/<job>"
    plan = ops.build(
        body.op, source, body.options, template, scratch, extras, _aac_encoder(), keyframes
    )
    return source, out_dir, plan, names


@router.post("/studio/probe")
async def post_probe(body: ProbeBody, request: Request) -> Any:
    try:
        if body.item_id:
            library: Library = request.app.state.library
            path = library.existing_primary(body.item_id)
        elif body.path:
            path = Path(body.path).expanduser()
        else:
            raise errors.AppError(code="SOURCE_NOT_FOUND")
        return await asyncio.to_thread(ops.probe_source, path)
    except errors.AppError as exc:
        return _error(exc, 404 if exc.code in ("SOURCE_NOT_FOUND", "ITEM_NOT_FOUND") else 400)


@router.post("/studio/plan")
async def post_plan(body: StudioBody) -> Any:
    try:
        _, _, plan, names = await asyncio.to_thread(_prepare, body)
    except errors.AppError as exc:
        return _error(exc)
    return {
        "steps": [
            {
                "kind": s.kind,
                "action": s.action,
                "command": shlex.join(s.argv) if s.kind == "ffmpeg" else "",
            }
            for s in plan.steps
        ],
        "notices": plan.notices,
        "blocking": plan.blocking,
        "outputs": names,
        "ext": plan.ext,
    }


@router.post("/studio/jobs")
async def post_job(body: StudioBody, request: Request) -> Any:
    try:
        source, out_dir, plan, _ = await asyncio.to_thread(_prepare, body)
    except errors.AppError as exc:
        return _error(exc)
    if plan.blocking:
        codes = ", ".join(n["code"] for n in plan.notices if n["level"] == "error")
        return _error(errors.AppError(code="SELECTION_INVALID", raw=codes))
    manager: JobManager = request.app.state.jobs
    job_id = uuid.uuid4().hex[:12]
    request_body = {
        "job_id": job_id,
        # Scratch space on the output's own volume, so the final move is an atomic rename.
        "work_dir": str(out_dir / ".vd-work" / job_id),
        "source_path": source["path"],
        "op": body.op,
        "options": body.options,
        "output_dir": str(out_dir),
        "scratch_root": str(out_dir / ".vd-work"),
        "output_name": body.output_name,
        "extra_paths": body.extra_paths,
    }
    job = manager.store.insert(
        {
            "id": job_id,
            "kind": "studio",
            "status": "queued",
            "stage": "queued",
            "title": naming.safe_filename(body.output_name),
            "source_url": None,
            "mode": "studio",
            "request": request_body,
        }
    )
    manager.publish({"type": "job", "job": public(job)})
    manager.wake()
    return public(job)


_PICK_FILE = [
    "-e",
    "on run argv",
    "-e",
    "POSIX path of (choose file with prompt (item 1 of argv))",
    "-e",
    "end run",
]


@router.post("/system/pick-file")
async def post_pick_file(body: PickFileBody) -> Any:
    if sys.platform != "darwin" or paths.fixture_mode():
        return _error(errors.AppError(code="PICKER_UNAVAILABLE"), 501)
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        *_PICK_FILE,
        body.prompt[:200],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return {"path": None}  # cancelled
    return {"path": out.decode().strip() or None}
