"""Hand a worker's YoutubeDL one site's part of Berk's Safari session -- and nothing else.

yt-dlp's own `cookiesfrombrowser` loads the *whole* Safari cookie jar (every site, every value)
and sends whatever matches the URLs it fetches. Here the jar is read, only the job's site's
cookies are kept (youtube.com, or reddit.com, instagram.com, x.com/twitter.com: see
`browser_session.SITES`), and they go straight into this YoutubeDL's in-memory jar: no file, no
other site's session. A store that cannot be read (no Full Disk Access) is COOKIES_UNREADABLE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app import browser_session, errors


def apply(ydl: Any, spec: list[str] | None) -> int:
    """Load the session described by `spec` (["safari", path, site]; jobs queued before
    2026-10-14 have no site and are YouTube's) into `ydl`. Returns how many cookies were added;
    0 and nothing done when there is no spec."""
    if not spec:
        return 0
    kind, path = spec[0], spec[1] if len(spec) > 1 else ""
    site = spec[2] if len(spec) > 2 else "youtube"
    if kind != "safari" or not path or site not in browser_session.SITES:
        raise errors.AppError(code="COOKIES_UNREADABLE", raw=f"unknown session {kind!r} {site!r}")
    try:
        data = Path(path).read_bytes()
    except OSError as exc:  # macOS refusing it without Full Disk Access, or it is gone
        raise errors.AppError(
            code="COOKIES_UNREADABLE", raw=f"{type(exc).__name__}: {exc}"
        ) from None
    from yt_dlp.cookies import parse_safari_cookies

    try:
        jar = parse_safari_cookies(data)
    except Exception as exc:
        raise errors.AppError(code="COOKIES_UNREADABLE", raw=type(exc).__name__) from None
    added = 0
    for cookie in jar:
        if browser_session.cookie_belongs(cookie.domain, site):
            ydl.cookiejar.set_cookie(cookie)
            added += 1
    return added


def scrub(info: dict[str, Any]) -> dict[str, Any]:
    """yt-dlp puts a `cookies` header string (with values) on formats it would send cookies
    for. An info.json written for Berk must never carry them."""
    info.pop("cookies", None)
    for key in ("formats", "requested_formats", "requested_downloads"):
        for fmt in info.get(key) or []:
            if isinstance(fmt, dict):
                fmt.pop("cookies", None)
    return info
