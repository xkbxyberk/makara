"""Which FFmpeg the app runs.

The release app's own build (installed by its setup assistant into `VD_BIN_DIR`) comes first.
Homebrew's plain `ffmpeg` lacks libass (subtitle burn-in), libwebp and zimg. Its `ffmpeg-full`
formula has them but is keg-only, so it is never on PATH. When it is installed it wins; otherwise
the `ffmpeg` on PATH is used. Resolved on every call (a few stat calls), so installing it is
picked up without a restart.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app import paths

FULL_KEG = paths.HOMEBREW / "opt" / "ffmpeg-full" / "bin"
FULL_FORMULA = "ffmpeg-full"


def _runnable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find(name: str) -> str | None:
    """Absolute path of `ffmpeg` or `ffprobe`, or None. Both always come from the same build."""
    if paths.bundled_tool("ffmpeg") and paths.bundled_tool("ffprobe"):
        return paths.bundled_tool(name)
    if _runnable(FULL_KEG / "ffmpeg") and _runnable(FULL_KEG / "ffprobe"):
        return str(FULL_KEG / name)
    return shutil.which(name)


def ffmpeg() -> str:
    return find("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return find("ffprobe") or "ffprobe"


def is_full(path: str | None) -> bool:
    """A build with libass, libwebp and zimg: ffmpeg-full, or the app's own (chosen for it)."""
    if path is None:
        return False
    return Path(path).parent in {FULL_KEG, paths.bin_dir()}
