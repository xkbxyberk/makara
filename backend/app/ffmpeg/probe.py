"""ffprobe as data. The worker trusts what is actually in a file over what a site claimed."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.ffmpeg import binaries


def ffprobe_path() -> str:
    return binaries.ffprobe()


def probe(path: Path) -> dict[str, Any]:
    argv = [
        ffprobe_path(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-show_chapters",
        str(path),
    ]
    out = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=60)
    data: dict[str, Any] = json.loads(out.stdout or "{}")
    return data


def streams_of(path: Path, codec_type: str | None = None) -> list[dict[str, Any]]:
    streams = probe(path).get("streams", [])
    return [s for s in streams if codec_type is None or s.get("codec_type") == codec_type]
