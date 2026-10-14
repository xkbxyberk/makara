"""Every filesystem location the app uses. Nothing writes outside these roots."""

from __future__ import annotations

import os
import platform
from pathlib import Path

SERVER_HOST = "127.0.0.1"
# The e2e suite uses its own port (VD_PORT) so it can run while the real app is open.
SERVER_PORT = int(os.environ.get("VD_PORT", "8787"))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "infojson"
MEDIA_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "media"
EXTENSION_DIR = PROJECT_ROOT / "macos" / "extension"

# Homebrew's prefix: /opt/homebrew on Apple silicon, /usr/local on Intel.
HOMEBREW = Path("/opt/homebrew") if platform.machine() == "arm64" else Path("/usr/local")

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "VideoDownloader"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Movies" / "VideoDownloader"


def data_dir() -> Path:
    """Where the database, settings and logs live. Overridable for tests."""
    override = os.environ.get("VD_DATA_DIR")
    path = Path(override) if override else APP_SUPPORT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def bin_dir() -> Path | None:
    """The tools the setup assistant installed (ffmpeg, ffprobe, deno, aria2c), which win over
    Homebrew's. Set by the release app; development and tests leave it unset."""
    override = os.environ.get("VD_BIN_DIR")
    return Path(override) if override else None


def bundled_tool(name: str) -> str | None:
    """`name` from `bin_dir()`, if it is there and runnable."""
    folder = bin_dir()
    if folder is None:
        return None
    path = folder / name
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


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
