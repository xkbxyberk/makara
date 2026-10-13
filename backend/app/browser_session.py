"""Berk's Safari session, for the YouTube videos that need a signed-in account (age-restricted,
members-only, private). Decided with Berk on 2026-10-13.

Only used when a video asks for it: everything is first tried without cookies, and only an
`AGE_RESTRICTED` / `LOGIN_REQUIRED` answer *for a YouTube URL* is retried once with the
session. yt-dlp's wiki warns that using an account carries a risk of a ban, so the session
never travels with ordinary downloads, and the workers receive only the `youtube.com` cookies
(app/workers/session.py), never the rest of the jar.

Safari keeps its cookies in its container, which macOS protects: the app needs Full Disk Access
to read them. The doctor decodes the jar in memory to look at cookie *names* (is YouTube signed
in?); no value is kept, logged or shown. Tests point VD_SAFARI_COOKIES at a file of their own,
and fixture mode without it has no session at all -- never Berk's real one.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app import paths

SAFARI_COOKIES = (
    Path.home()
    / "Library"
    / "Containers"
    / "com.apple.Safari"
    / "Data"
    / "Library"
    / "Cookies"
    / "Cookies.binarycookies"
)
# Present only when YouTube is signed in (names only; values are never looked at).
YOUTUBE_LOGIN_COOKIES = {"SAPISID", "__Secure-3PAPISID", "__Secure-1PSID", "SID", "LOGIN_INFO"}
AUTH_CODES = {"AGE_RESTRICTED", "LOGIN_REQUIRED"}


YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def is_youtube_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def cookies_path() -> Path | None:
    override = os.environ.get("VD_SAFARI_COOKIES")
    if override:
        return Path(override)
    if paths.fixture_mode():
        return None
    return SAFARI_COOKIES


def ytdlp_option() -> list[str] | None:
    """`cookiesfrombrowser` for yt-dlp, with the explicit file (so tests can redirect it)."""
    path = cookies_path()
    return ["safari", str(path)] if path is not None else None


def status() -> dict[str, Any]:
    """Can the server read the session, and is YouTube signed in there?"""
    path = cookies_path()
    if path is None or not path.exists():
        return {"available": False, "readable": False, "youtube_signed_in": None}
    try:
        data = path.read_bytes()
    except PermissionError:
        # macOS refuses without Full Disk Access ("Operation not permitted").
        return {"available": True, "readable": False, "youtube_signed_in": None}
    except OSError:
        return {"available": True, "readable": False, "youtube_signed_in": None}
    return {"available": True, "readable": True, "youtube_signed_in": _youtube_signed_in(data)}


def _youtube_signed_in(data: bytes) -> bool | None:
    try:
        from yt_dlp.cookies import parse_safari_cookies

        jar = parse_safari_cookies(data)
    except Exception:  # an unknown file layout: say nothing rather than guess
        return None
    return any(
        cookie.name in YOUTUBE_LOGIN_COOKIES and cookie.domain.lstrip(".").endswith("youtube.com")
        for cookie in jar
    )
