"""User settings, persisted as a small JSON file next to the database."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from app import paths

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

    def __post_init__(self) -> None:
        if not self.download_dir:
            self.download_dir = str(paths.download_dir())
        self.concurrency = max(1, min(int(self.concurrency), 6))
        if self.default_mode not in MODES:
            self.default_mode = "mkv"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
