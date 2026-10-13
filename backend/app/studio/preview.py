"""Stüdyo's preview: a copy of the source that macOS's own player (AVFoundation) can play and step
through frame by frame.

AVFoundation opens neither MKV nor WebM, and not VP9 or (reliably) AV1 even in MP4 -- measured on
this Mac, 2026-10-13 -- while most downloads are archive MKVs with VP9/AV1 and Opus. So the
native Stüdyo asks for a preview: H.264/HEVC video is copied as is (ready in a moment); anything
else is re-encoded to H.264 (VideoToolbox when the FFmpeg build has it), at most 720 lines high.
Timestamps pass through untouched (`-fps_mode passthrough`), so frame N of the preview is frame
N of the source and a cut chosen on the preview lands on the same frame of the source.

Previews are a cache in the app's data folder (never next to Berk's files), keyed by path, size
and modification time, oldest first out above a size cap. One FFmpeg at a time per source; the
process shares the server's process group, so it stops with the server.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import errors, paths
from app.ffmpeg import binaries
from app.studio import ops

log = logging.getLogger(__name__)

CACHE_LIMIT_BYTES = 3 * 1024**3
COPY_VIDEO = {"h264", "hevc"}  # what AVFoundation plays and steps through reliably
COPY_AUDIO = {"aac", "alac"}  # what the MP4/M4A muxer takes as is (it refuses MP3 in an .m4a)


@dataclass(slots=True)
class Preview:
    state: str  # "running" | "ready" | "failed"
    path: Path
    progress: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "path": str(self.path) if self.state == "ready" else None,
            "progress": round(self.progress, 3),
            "error": self.error,
        }


def cache_dir() -> Path:
    return paths.data_dir() / "preview-cache"


def key_for(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def plan(source: dict[str, Any], output: Path, hardware: bool) -> list[str]:
    """The FFmpeg command for one preview (pure, so tests can read it)."""
    video = next(
        (s for s in source["streams"] if s["type"] == "video" and not s["attached_pic"]), None
    )
    audio = next((s for s in source["streams"] if s["type"] == "audio"), None)
    argv = [binaries.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    argv += ["-i", source["path"]]
    if video is not None:
        argv += ["-map", f"0:{video['index']}"]
        if video["codec"] in COPY_VIDEO:
            argv += ["-c:v", "copy"]
        else:
            scale = ["-vf", "scale=-2:'min(720,ih)'"]
            encoder = (
                ["-c:v", "h264_videotoolbox", "-b:v", "5M", "-allow_sw", "1"]
                if hardware
                else ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"]
            )
            argv += [*scale, *encoder, "-pix_fmt", "yuv420p"]
        argv += ["-fps_mode", "passthrough"]
    if audio is not None:
        argv += ["-map", f"0:{audio['index']}"]
        argv += (
            ["-c:a", "copy"] if audio["codec"] in COPY_AUDIO else ["-c:a", "aac", "-b:a", "160k"]
        )
    argv += ["-sn", "-dn", "-map_metadata", "-1", "-movflags", "+faststart"]
    argv += ["-progress", "pipe:1", "-nostats", str(output)]
    return argv


class PreviewManager:
    def __init__(self) -> None:
        self._previews: dict[str, Preview] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        # Half-made copies of a server that was killed: never finished, never counted.
        for leftover in cache_dir().glob("*.part.*") if cache_dir().is_dir() else []:
            with contextlib.suppress(OSError):
                leftover.unlink()

    def _forget_if_gone(self, key: str) -> None:
        """A "ready" copy the cache evicted (or someone deleted) is made again on request."""
        preview = self._previews.get(key)
        if preview is not None and preview.state == "ready" and not preview.path.is_file():
            del self._previews[key]

    def status(self, source_path: Path) -> dict[str, Any]:
        key = key_for(source_path)
        self._forget_if_gone(key)
        preview = self._previews.get(key)
        if preview is None:
            existing = self._ready_file(key)
            if existing is None:
                return {"state": "none", "path": None, "progress": 0.0, "error": None}
            preview = self._previews[key] = Preview("ready", existing, 1.0)
        return preview.as_dict()

    def _ready_file(self, key: str) -> Path | None:
        for ext in ("mp4", "m4a"):
            candidate = cache_dir() / f"{key}.{ext}"
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        return None

    async def start(self, source_path: Path) -> dict[str, Any]:
        """Start (or join) the preview of `source_path`; returns its status at once."""
        source = await asyncio.to_thread(ops.probe_source, source_path)
        if not any(s["type"] in ("video", "audio") for s in source["streams"]):
            raise errors.AppError(code="SOURCE_NOT_MEDIA", raw=str(source_path))
        key = key_for(source_path)
        self._forget_if_gone(key)
        current = self._previews.get(key)
        if current is not None and current.state in ("running", "ready"):
            return current.as_dict()
        existing = self._ready_file(key)
        if existing is not None:
            self._previews[key] = Preview("ready", existing, 1.0)
            return self._previews[key].as_dict()
        has_video = any(s["type"] == "video" and not s["attached_pic"] for s in source["streams"])
        output = cache_dir() / f"{key}.{'mp4' if has_video else 'm4a'}"
        preview = self._previews[key] = Preview("running", output)
        self._tasks[key] = asyncio.create_task(self._run(key, source, preview))
        return preview.as_dict()

    async def _run(self, key: str, source: dict[str, Any], preview: Preview) -> None:
        cache_dir().mkdir(parents=True, exist_ok=True)
        partial = preview.path.with_name(preview.path.stem + ".part" + preview.path.suffix)
        argv = plan(source, partial, hardware=_has_videotoolbox())
        duration = source.get("duration") or 0
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            self._procs[key] = proc
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if line.startswith("out_time_us=") and duration:
                    with contextlib.suppress(ValueError):
                        preview.progress = min(0.99, int(line.split("=", 1)[1]) / 1e6 / duration)
            stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
            code = await proc.wait()
            if code != 0 or not partial.is_file() or partial.stat().st_size == 0:
                raise errors.AppError(code="PREVIEW_FAILED", raw=stderr[-2000:] or f"exit {code}")
            os.replace(partial, preview.path)
            preview.state, preview.progress = "ready", 1.0
            with contextlib.suppress(OSError):  # a full cache is no reason to fail a good copy
                await asyncio.to_thread(_evict, keep=preview.path)
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError, KeyError):
                self._procs[key].kill()
            raise
        except (OSError, errors.AppError) as exc:
            preview.state = "failed"
            preview.error = exc.code if isinstance(exc, errors.AppError) else "PREVIEW_FAILED"
            log.warning("preview failed: %s", exc)
        finally:
            self._procs.pop(key, None)
            with contextlib.suppress(OSError):
                partial.unlink()

    async def stop(self) -> None:
        for proc in list(self._procs.values()):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        for task in list(self._tasks.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def _has_videotoolbox() -> bool:
    from app.doctor import listing_has

    try:
        import subprocess

        encoders = subprocess.run(
            [binaries.ffmpeg(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return listing_has(encoders, "h264_videotoolbox")


def _evict(keep: Path) -> None:
    """Oldest previews out while the cache is above its cap (never the one just made)."""
    files = sorted(
        (p for p in cache_dir().glob("*") if p.is_file() and ".part" not in p.name),
        key=lambda p: p.stat().st_mtime,
    )
    total = sum(p.stat().st_size for p in files)
    for path in files:
        if total <= CACHE_LIMIT_BYTES:
            break
        if path == keep:
            continue
        total -= path.stat().st_size
        with contextlib.suppress(OSError):
            path.unlink()
