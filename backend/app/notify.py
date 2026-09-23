"""macOS notifications and Finder reveal. Text arrives from the UI (tr.ts), never built here."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app import errors, paths

# The title and body are passed as AppleScript *arguments*, never spliced into the script, so
# a video title containing quotes cannot become AppleScript code.
_SCRIPT = [
    "-e",
    "on run argv",
    "-e",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "-e",
    "end run",
]


def notify(title: str, body: str) -> bool:
    if paths.fixture_mode() or sys.platform != "darwin":
        return False
    argv = ["osascript", *_SCRIPT, title[:200], body[:500]]
    subprocess.run(argv, capture_output=True, timeout=10, check=False)
    return True


def reveal(path_text: str, root: Path) -> bool:
    """Select a downloaded file in Finder. Only paths inside the download root are accepted."""
    base = root.expanduser().resolve()
    target = Path(path_text).expanduser().resolve()
    if not target.is_relative_to(base):
        raise errors.AppError(code="PATH_OUTSIDE_ROOT", raw=str(target))
    if not target.exists():
        raise errors.AppError(code="FILE_MISSING", raw=str(target))
    if paths.fixture_mode() or sys.platform != "darwin":
        return False
    subprocess.run(["open", "-R", str(target)], capture_output=True, timeout=10, check=False)
    return True
