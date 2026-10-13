"""Finder reveal. (Notifications are posted by the app itself.)"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app import errors, paths


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
