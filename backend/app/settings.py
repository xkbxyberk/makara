"""User settings, persisted as a small JSON file next to the database."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from app import errors, paths

DEFAULT_TEMPLATE = (
    "%(extractor_key)s/%(channel,uploader|Unknown)s/"
    "%(upload_date>%Y-%m-%d|0000-00-00)s - %(title)s [%(id)s].%(ext)s"
)
MODES = ("mkv", "compat_mp4", "separate", "audio")


@dataclass(slots=True)
class Settings:
    download_dir: str = ""
    filename_template: str = DEFAULT_TEMPLATE
    concurrency: int = 2
    default_mode: str = "mkv"
    clipboard_watch: bool = False  # opt-in, agreed with Berk
    notifications: bool = True
    # Retry a video that needs a signed-in account with the Safari session (Berk, 2026-10-13).
    safari_login: bool = True

    def __post_init__(self) -> None:
        if not self.download_dir:
            self.download_dir = str(paths.download_dir())
        self.concurrency = max(1, min(int(self.concurrency), 6))
        if self.default_mode not in MODES:
            self.default_mode = "mkv"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Folders a download root may never be, nor sit inside: the app creates folders and scans
# everything under the root, and the library reveals files there.
_SYSTEM_TREES = (
    "/System",
    "/Library",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/private/etc",
    "/Applications",
    "/cores",
    "/opt",
    "/private/var/db",
    "/dev",
)
_NEVER_EXACTLY = ("/", "/Users", "/Volumes", "/private", "/private/var")


def validate_download_dir(text: str) -> Path:
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise errors.AppError(code="DOWNLOAD_DIR_NOT_ABSOLUTE", raw=text)
    resolved = path.resolve()
    home = Path.home().resolve()
    unsafe = (
        str(resolved) in _NEVER_EXACTLY
        or resolved == home
        or resolved.is_relative_to(home / "Library")
        or any(resolved.is_relative_to(Path(t).resolve()) for t in _SYSTEM_TREES)
    )
    if unsafe:
        raise errors.AppError(code="DOWNLOAD_DIR_UNSAFE", raw=text)
    if resolved.exists() and not resolved.is_dir():
        raise errors.AppError(code="DOWNLOAD_DIR_NOT_A_FOLDER", raw=text)
    if not resolved.exists() and not resolved.parent.is_dir():
        raise errors.AppError(code="DOWNLOAD_DIR_MISSING", raw=text)
    probe_dir = resolved if resolved.exists() else resolved.parent
    if not os.access(probe_dir, os.W_OK):
        raise errors.AppError(code="DOWNLOAD_DIR_NOT_WRITABLE", raw=text)
    return resolved


def _file() -> Path:
    return paths.data_dir() / "settings.json"


def load() -> Settings:
    try:
        raw = json.loads(_file().read_text())
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save(settings: Settings) -> Settings:
    _file().write_text(json.dumps(settings.as_dict(), indent=2))
    return settings
