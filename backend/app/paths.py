"""Every filesystem location the app uses. Nothing writes outside these roots."""

from __future__ import annotations

import os
from pathlib import Path

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8787

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "infojson"
MEDIA_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "media"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "VideoDownloader"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Movies" / "VideoDownloader"


def data_dir() -> Path:
    """Where the database, settings and logs live. Overridable for tests."""
    override = os.environ.get("VD_DATA_DIR")
    path = Path(override) if override else APP_SUPPORT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_dir() -> Path:
    override = os.environ.get("VD_DOWNLOAD_DIR")
    return Path(override) if override else DEFAULT_DOWNLOAD_DIR


def fixture_media_base() -> str:
    """Where the generated test media is served in fixture mode (by this very server)."""
    default = f"http://{SERVER_HOST}:{SERVER_PORT}/fixture-media"
    return os.environ.get("VD_FIXTURE_MEDIA_BASE", default)


def fixture_mode() -> bool:
    """When on, Inspect reads recorded info dicts instead of touching the network."""
    return os.environ.get("VD_FIXTURE_MODE") == "1"
