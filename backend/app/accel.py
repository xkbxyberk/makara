"""Faster downloads (Berk, 2026-10-14: "IDM-style", aria2c approved).

Two mechanisms, both yt-dlp's own: fragmented formats (HLS/DASH, most sites) download several
fragments at once (`concurrent_fragment_downloads`); a single-file HTTP format is fetched by
aria2c over several connections with byte ranges. The worker gets the result of `network()`
when it starts, so a changed setting applies to the next start or resume, never mid-file.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from app import paths
from app.settings import Settings

HOMEBREW_ARIA2C = paths.HOMEBREW / "bin" / "aria2c"


def aria2c() -> str | None:
    """aria2c's absolute path, or None. The offline suite opts in with VD_ARIA2C (a path), so
    no test depends on what happens to be installed on the machine running it."""
    if paths.fixture_mode():
        configured = os.environ.get("VD_ARIA2C")
        return configured if configured and os.access(configured, os.X_OK) else None
    if bundled := paths.bundled_tool("aria2c"):
        return bundled
    if HOMEBREW_ARIA2C.is_file() and os.access(HOMEBREW_ARIA2C, os.X_OK):
        return str(HOMEBREW_ARIA2C)
    return shutil.which("aria2c")


def network(settings: Settings) -> dict[str, Any]:
    return {
        "accelerate": settings.accelerate,
        "connections": settings.connections if settings.accelerate else 1,
        "rate_limit": settings.rate_limit or None,  # bytes per second, for the whole download
        "aria2c": aria2c() if settings.accelerate and settings.connections > 1 else None,
    }
