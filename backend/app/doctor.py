"""Dependency doctor: what is installed, what works, and what to do about it.

Every check returns a stable id and status; the frontend turns those into Turkish.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
from typing import Any

from app.system import installed_ytdlp
from app.ytdlp.params import find_js_runtimes

OK, WARN, ERROR = "ok", "warn", "error"

# Capabilities this machine's FFmpeg build must have for a feature to be offered at all.
FFMPEG_CAPABILITIES: dict[str, tuple[str, str]] = {
    "libx264": ("encoder", "libx264"),
    "libx265": ("encoder", "libx265"),
    "libsvtav1": ("encoder", "libsvtav1"),
    "videotoolbox_h264": ("encoder", "h264_videotoolbox"),
    "videotoolbox_hevc": ("encoder", "hevc_videotoolbox"),
    "aac": ("encoder", "aac"),
    "libopus": ("encoder", "libopus"),
    "libmp3lame": ("encoder", "libmp3lame"),
    "flac": ("encoder", "flac"),
    "webp": ("encoder", "libwebp"),
    "gif": ("encoder", "gif"),
    "loudnorm": ("filter", "loudnorm"),
    "palettegen": ("filter", "palettegen"),
    # libass. Its absence is why burning subtitles into the picture is not offered.
    "subtitles_filter": ("filter", "subtitles"),
}


def listing_has(listing: str, name: str) -> bool:
    """`ffmpeg -encoders`/`-filters` lines read " A....D aac   AAC (...)": flags, then the name.
    Matching any word would let "aac (AudioToolbox) (codec aac)" on the aac_at line claim the
    native encoder, so only the name column counts."""
    return any(
        len(tokens) > 1 and tokens[1] == name
        for tokens in (line.split() for line in listing.splitlines())
    )


def _run(argv: list[str], timeout: int = 20) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout + proc.stderr


def _ytdlp_check() -> dict[str, Any]:
    try:
        from yt_dlp import version as ytv
    except ImportError:
        return {
            "id": "yt_dlp",
            "status": ERROR,
            "values": {},
            "fix": {"kind": "command", "command": "uv sync"},
        }
    try:
        ejs = importlib.metadata.version("yt-dlp-ejs")
    except importlib.metadata.PackageNotFoundError:
        ejs = ""
    installed = installed_ytdlp()
    return {
        "id": "yt_dlp",
        "status": OK if ejs else WARN,
        "values": {
            "version": installed["version"],
            "channel": installed["channel"],
            "origin": ytv.ORIGIN,
            "ejs_version": ejs,
        },
        # `yt-dlp -U` refuses pip/uv installs, and `uv pip install -U` would be reverted by the
        # next `uv run` (it syncs to uv.lock). Upgrading the lock is what sticks.
        "fix": {
            "kind": "command",
            "command": "uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync",
        },
    }


def _js_runtime_check() -> dict[str, Any]:
    runtimes = find_js_runtimes()
    return {
        "id": "js_runtime",
        # Without one, yt-dlp does not fail -- it silently drops the `web` client and
        # some YouTube formats go missing. That deserves a warning, not a green tick.
        "status": OK if runtimes else ERROR,
        "values": {
            "found": [{"name": r.name, "path": r.path, "version": r.version} for r in runtimes],
            "active": runtimes[0].name if runtimes else None,
        },
        "fix": {"kind": "command", "command": "brew install deno"},
    }


def _ffmpeg_check() -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return {
            "id": "ffmpeg",
            "status": ERROR,
            "values": {"capabilities": {}},
            "fix": {"kind": "command", "command": "brew install ffmpeg"},
        }
    version_line = (_run([ffmpeg, "-version"]).splitlines() or [""])[0]
    encoders = _run([ffmpeg, "-hide_banner", "-encoders"])
    filters = _run([ffmpeg, "-hide_banner", "-filters"])
    capabilities = {}
    for name, (kind, needle) in FFMPEG_CAPABILITIES.items():
        haystack = encoders if kind == "encoder" else filters
        capabilities[name] = listing_has(haystack, needle)
    missing_optional = [k for k in ("subtitles_filter", "webp") if not capabilities[k]]
    return {
        "id": "ffmpeg",
        "status": WARN if missing_optional else OK,
        "values": {
            "ffmpeg_path": ffmpeg,
            "ffprobe_path": ffprobe,
            "version": version_line,
            "capabilities": capabilities,
            "missing_optional": missing_optional,
        },
        "fix": {"kind": "none", "command": ""},
    }


def run_doctor() -> dict[str, Any]:
    checks = [_ytdlp_check(), _js_runtime_check(), _ffmpeg_check()]
    worst = (
        ERROR
        if any(c["status"] == ERROR for c in checks)
        else (WARN if any(c["status"] == WARN for c in checks) else OK)
    )
    return {"status": worst, "checks": checks}
