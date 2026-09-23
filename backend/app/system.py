"""Things that touch the Mac itself: the folder picker, the yt-dlp updater, the clipboard.

All of it uses argv lists. User-facing text (the picker's prompt) arrives from the UI and is
passed to AppleScript as an argument, never spliced into the script.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from app import errors, paths

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
CLIPBOARD_POLL_SECONDS = 1.0

_PICK_FOLDER = [
    "-e",
    "on run argv",
    "-e",
    "POSIX path of (choose folder with prompt (item 1 of argv))",
    "-e",
    "end run",
]


def pick_folder(prompt: str) -> str | None:
    """The native macOS folder picker. None when the user cancels."""
    if sys.platform != "darwin" or paths.fixture_mode():
        raise errors.AppError(code="PICKER_UNAVAILABLE")
    proc = subprocess.run(
        ["osascript", *_PICK_FOLDER, prompt[:200]], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return None  # "User canceled." is AppleScript error -128
    return proc.stdout.strip().rstrip("/") or None


def installed_ytdlp() -> dict[str, str]:
    """Read from the installed package metadata, not the imported module: after an update the
    server's already-imported yt_dlp is stale, while every new worker process gets the new one."""
    version = importlib.metadata.version("yt-dlp")
    try:
        ejs = importlib.metadata.version("yt-dlp-ejs")
    except importlib.metadata.PackageNotFoundError:
        ejs = ""
    return {"version": version, "channel": "nightly" if ".dev" in version else "stable", "ejs": ejs}


def update_ytdlp_argv() -> list[list[str]]:
    """Upgrade yt-dlp *in the lock file* and then sync.

    A plain `uv pip install -U` would be silently reverted: `uv run` syncs the environment to
    uv.lock on every launch. yt-dlp-ejs is upgraded together because yt-dlp pins it exactly.
    """
    uv = shutil.which("uv") or "uv"
    return [
        [uv, "lock", "--upgrade-package", "yt-dlp", "--upgrade-package", "yt-dlp-ejs"],
        [uv, "sync"],
    ]


def update_ytdlp() -> dict[str, Any]:
    if paths.fixture_mode():
        raise errors.AppError(code="UPDATE_UNAVAILABLE", raw="fixture mode never touches the venv")
    before = installed_ytdlp()
    log: list[str] = []
    for argv in update_ytdlp_argv():
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                cwd=paths.PROJECT_ROOT,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:  # no uv, or it hung
            raise errors.AppError(code="UPDATE_FAILED", raw=f"{argv[0]}: {exc}") from None
        log.append(f"$ {' '.join(argv)}\n{proc.stdout}{proc.stderr}")
        if proc.returncode != 0:
            raise errors.AppError(code="UPDATE_FAILED", raw="\n".join(log)[-6000:])
    importlib.invalidate_caches()
    after = installed_ytdlp()
    return {
        "before": before,
        "after": after,
        "changed": before != after,
        "log": "\n".join(log)[-6000:],
    }


class ClipboardWatcher:
    """Opt-in: offers to inspect a link when Berk copies one.

    Polls NSPasteboard's change counter, which is cheap and does not read the clipboard; the
    contents are read only when the counter moves, and only while the setting is on. Whatever
    was already on the clipboard when the watcher was switched on is ignored.
    """

    def __init__(
        self,
        enabled: Callable[[], bool],
        publish: Callable[[dict[str, Any]], None],
        board: Any = None,
    ) -> None:
        self.enabled = enabled
        self.publish = publish
        self.board = board  # anything with changeCount() and text(); AppKit's by default
        self._task: asyncio.Task[None] | None = None

    @staticmethod
    def available() -> bool:
        if sys.platform != "darwin" or paths.fixture_mode():
            return False
        try:
            import AppKit  # noqa: F401  (pyobjc, installed with pywebview)
        except ImportError:
            return False
        return True

    def start(self) -> None:
        if self.board is not None or self.available():
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        board = self.board or _AppKitBoard()
        last: int | None = None
        while True:
            await asyncio.sleep(CLIPBOARD_POLL_SECONDS)
            if not self.enabled():
                last = None
                continue
            count = int(board.changeCount())
            if last is None or count == last:
                last = count
                continue
            last = count
            url = str(board.text() or "").strip()
            if url and len(url) <= 2048 and URL_RE.match(url):
                self.publish({"type": "clipboard", "url": url})


class _AppKitBoard:
    def __init__(self) -> None:
        import AppKit

        self._appkit = AppKit
        self._board = AppKit.NSPasteboard.generalPasteboard()

    def changeCount(self) -> int:  # mirrors NSPasteboard
        return int(self._board.changeCount())

    def text(self) -> str | None:
        value = self._board.stringForType_(self._appkit.NSPasteboardTypeString)
        return str(value) if value is not None else None
