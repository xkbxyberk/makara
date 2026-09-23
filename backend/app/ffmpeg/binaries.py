"""Which FFmpeg the app runs.

Homebrew's plain `ffmpeg` lacks libass (subtitle burn-in), libwebp and zimg. Its `ffmpeg-full`
formula has them but is keg-only, so it is never on PATH. When it is installed it wins; otherwise
the `ffmpeg` on PATH is used. Resolved on every call (a few stat calls), so installing it is
picked up without a restart.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

FULL_KEG = Path("/opt/homebrew/opt/ffmpeg-full/bin")
FULL_FORMULA = "ffmpeg-full"


def _runnable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find(name: str) -> str | None:
    """Absolute path of `ffmpeg` or `ffprobe`, or None. Both always come from the same build."""
    if _runnable(FULL_KEG / "ffmpeg") and _runnable(FULL_KEG / "ffprobe"):
        return str(FULL_KEG / name)
    return shutil.which(name)


def ffmpeg() -> str:
    return find("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return find("ffprobe") or "ffprobe"


def is_full(path: str | None) -> bool:
    return path is not None and Path(path).parent == FULL_KEG
