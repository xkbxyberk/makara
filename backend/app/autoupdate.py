"""yt-dlp keeps itself current (P6e): once a week, in the background, when nothing is
downloading. YouTube changes often, and an old yt-dlp loses formats before it fails outright.

The update is the Doctor button's (`system.update_ytdlp`: the lock file, then `uv sync`). While
it runs the queue starts nothing new: a worker importing yt-dlp while its files are swapped
would break. The outcome is kept in `<data>/ytdlp-update.json` and shown in Sistem.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from app import errors, paths, system
from app import settings as settings_store

log = logging.getLogger("videodownloader.autoupdate")
INTERVAL_SECONDS = 7 * 24 * 3600
CHECK_SECONDS = 3600
FIRST_CHECK_SECONDS = 120  # not while the app is still starting up


def _file() -> Path:
    return paths.data_dir() / "ytdlp-update.json"


def last() -> dict[str, Any]:
    """The last automatic update: {"at", "ok", "code"?, "version"?}, or {} before the first."""
    try:
        data = json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def due(now: float | None = None) -> bool:
    if paths.fixture_mode() or not settings_store.load().auto_update_ytdlp:
        return False
    return (now or time.time()) - float(last().get("at") or 0) >= INTERVAL_SECONDS


async def run_once(manager: Any) -> dict[str, Any] | None:
    if not due() or manager.active:
        return None
    manager.hold = True
    try:
        result = await asyncio.to_thread(system.update_ytdlp)
        record: dict[str, Any] = {
            "at": time.time(),
            "ok": True,
            "version": result["after"]["version"],
        }
    except errors.AppError as exc:
        record = {"at": time.time(), "ok": False, "code": exc.code}
    finally:
        manager.hold = False
        manager.wake()
    with contextlib.suppress(OSError):
        _file().write_text(json.dumps(record))
    log.info("automatic yt-dlp update: %s", record)
    return record


def start(manager: Any) -> asyncio.Task[None]:
    async def loop() -> None:
        await asyncio.sleep(FIRST_CHECK_SECONDS)
        while True:
            try:
                await run_once(manager)
            except Exception:
                log.exception("automatic yt-dlp update failed")
            await asyncio.sleep(CHECK_SECONDS)

    return asyncio.create_task(loop())
