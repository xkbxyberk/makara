"""Berk's Safari session, for videos that need a signed-in account: YouTube (age-restricted,
members-only, private; decided with Berk on 2026-10-13), and since 2026-10-14 Reddit (its API
no longer answers anonymously; NSFW posts), Instagram and X (sensitive or private posts), where
Berk signed in for this.

Only used when a video asks for it: everything is first tried without cookies, and only an
`AGE_RESTRICTED` / `LOGIN_REQUIRED` answer *for one of these sites' URLs* is retried once with
the session. yt-dlp's wiki warns that using an account carries a risk of a ban, so the session
never travels with ordinary downloads, and a worker receives only *that site's* cookies
(app/workers/session.py), never the rest of the jar.

Safari keeps its cookies in its container, which macOS protects: the app needs Full Disk Access
to read them. The doctor decodes the jar in memory to look at cookie *names* (is YouTube signed
in?); no value is kept, logged or shown. Tests point VD_SAFARI_COOKIES at a file of their own,
and fixture mode without it has no session at all -- never Berk's real one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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
AUTH_CODES = {"AGE_RESTRICTED", "LOGIN_REQUIRED"}


@dataclass(frozen=True)
class Site:
    hosts: tuple[str, ...]  # page addresses that may be retried with the session
    cookie_domains: tuple[str, ...]  # the only cookies its worker is given
    login_cookies: frozenset[str]  # present only when signed in (names; values never read)
    # Which first answers send the request again with the session. YouTube: only "sign in".
    # The others hide what a signed-out visitor may not see behind other answers: Reddit's
    # NSFW/"gated" subreddits answer 403, X shows a sensitive post "with no video".
    retry_codes: frozenset[str] = frozenset({"AGE_RESTRICTED", "LOGIN_REQUIRED"})
    # Reddit's API stopped answering signed-out visitors (401s, "authentication required",
    # 500s; measured 14 Oct): there the first try is already the signed-in one.
    session_first: bool = False


_SIGNED_OUT_HIDES = frozenset(
    {"AGE_RESTRICTED", "LOGIN_REQUIRED", "FORBIDDEN", "VIDEO_UNAVAILABLE", "UNKNOWN"}
)


SITES = {
    "youtube": Site(
        ("youtube.com", "youtu.be", "youtube-nocookie.com"),
        ("youtube.com",),
        frozenset({"SAPISID", "__Secure-3PAPISID", "__Secure-1PSID", "SID", "LOGIN_INFO"}),
    ),
    "reddit": Site(
        ("reddit.com", "redd.it"),
        ("reddit.com",),
        frozenset({"reddit_session"}),
        _SIGNED_OUT_HIDES,
        session_first=True,
    ),
    "instagram": Site(
        ("instagram.com",), ("instagram.com",), frozenset({"sessionid"}), _SIGNED_OUT_HIDES
    ),
    "x": Site(
        ("x.com", "twitter.com"),
        ("x.com", "twitter.com"),
        frozenset({"auth_token"}),
        _SIGNED_OUT_HIDES,
    ),
}
YOUTUBE_LOGIN_COOKIES = SITES["youtube"].login_cookies
# Brand names, the same in every language (the doctor lists the signed-in ones).
SITE_NAMES = {"youtube": "YouTube", "reddit": "Reddit", "instagram": "Instagram", "x": "X"}


def _within(host: str, domains: tuple[str, ...]) -> bool:
    host = host.lstrip(".").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def site_of(url: str) -> str | None:
    """Which session site a page belongs to, by its exact host (never a look-alike)."""
    host = (urlsplit(url).hostname or "").lower()
    return next((name for name, site in SITES.items() if _within(host, site.hosts)), None)


def is_youtube_url(url: str) -> bool:
    return site_of(url) == "youtube"


def cookie_belongs(domain: str, site: str) -> bool:
    return site in SITES and _within(domain, SITES[site].cookie_domains)


def cookies_path() -> Path | None:
    override = os.environ.get("VD_SAFARI_COOKIES")
    if override:
        return Path(override)
    if paths.fixture_mode():
        return None
    return SAFARI_COOKIES


def ytdlp_option(site: str = "youtube") -> list[str] | None:
    """The session a job carries: ["safari", file, site]. The file is explicit (so tests can
    redirect it); the site decides which cookies its worker may load."""
    path = cookies_path()
    return ["safari", str(path), site] if path is not None else None


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
    signed_in = _signed_in(data)
    out: dict[str, Any] = {
        "available": True,
        "readable": True,
        "youtube_signed_in": None if signed_in is None else signed_in["youtube"],
    }
    if signed_in is not None:
        out["signed_in"] = signed_in
    return out


def _signed_in(data: bytes) -> dict[str, bool] | None:
    """Per site: does the jar hold its login cookie? Names only."""
    try:
        from yt_dlp.cookies import parse_safari_cookies

        jar = parse_safari_cookies(data)
    except Exception:  # an unknown file layout: say nothing rather than guess
        return None
    return {
        name: any(
            cookie.name in site.login_cookies and _within(cookie.domain, site.cookie_domains)
            for cookie in jar
        )
        for name, site in SITES.items()
    }
