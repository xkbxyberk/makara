"""Raw yt-dlp/FFmpeg failures in, machine-readable codes out.

The backend never returns Turkish text. The app owns every user-facing string (its
`Localizable.xcstrings`; the Safari extension has `_locales/tr/messages.json`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Ordered: the first pattern that matches wins, so put the specific ones first.
_PATTERNS: list[tuple[str, str]] = [
    # Safari's cookie store without Full Disk Access, or an unreadable one.
    ("COOKIES_UNREADABLE", r"binarycookies|safari cookies database"),
    ("DRM_PROTECTED", r"\bdrm\b|protected by drm|widevine|playready"),
    # YouTube's anti-bot wall says "sign in", but the video is public -- it is the IP that is
    # flagged. Must be tested before LOGIN_REQUIRED.
    ("BOT_CHECK", r"not a bot|confirm you.?re not a robot|unusual traffic"),
    ("RATE_LIMITED", r"http error 429|too many requests"),
    ("FORBIDDEN", r"http error 403|forbidden"),
    ("VIDEO_UNAVAILABLE", r"http error 404|http error 410"),
    ("AGE_RESTRICTED", r"age.?restrict|confirm your age|inappropriate for some users"),
    (
        "LOGIN_REQUIRED",
        r"log in|login|sign in|account credentials|--cookies|private video|members-only",
    ),
    ("GEO_RESTRICTED", r"available in your country|geo.?restrict|geo.?block"),
    (
        "VIDEO_UNAVAILABLE",
        r"video unavailable|has been removed|no longer available|this video is not available",
    ),
    ("LIVE_NOT_STARTED", r"premieres in|live event will begin|is not yet available"),
    ("UNSUPPORTED_SITE", r"unsupported url|no suitable extractor|is not a valid url"),
    ("NO_JS_RUNTIME", r"no supported javascript runtime|signature solving failed"),
    (
        "NETWORK",
        r"unable to download|connection|timed out|timeout|temporary failure|getaddrinfo|ssl",
    ),
]

UNKNOWN = "UNKNOWN"

# yt-dlp does not fail when the JS runtime is missing; it warns and quietly loses formats.
_WARNING_PATTERNS: list[tuple[str, str]] = [
    ("NO_JS_RUNTIME", r"no supported javascript runtime"),
    ("FORMATS_MAY_BE_MISSING", r"signature solving failed|some formats may be missing"),
]


@dataclass(slots=True)
class AppError(Exception):
    """An error with a stable code; `raw` is kept so the UI can show the real log."""

    code: str
    raw: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "raw": self.raw, "detail": self.detail}


def classify(message: str) -> str:
    """Map a raw error message onto one of the known codes. URLs are left out first: an
    address like ".../login?next=/" says nothing about why it failed (and once made an
    unsupported page look like one that needs an account)."""
    text = re.sub(r"https?://\S+", " ", message.lower())
    for code, pattern in _PATTERNS:
        if re.search(pattern, text):
            return code
    return UNKNOWN


def classify_warnings(messages: list[str]) -> list[str]:
    found: list[str] = []
    for message in messages:
        for code, pattern in _WARNING_PATTERNS:
            if re.search(pattern, message.lower()) and code not in found:
                found.append(code)
    return found


def from_exception(exc: BaseException) -> AppError:
    raw = str(exc) or exc.__class__.__name__
    return AppError(code=classify(raw), raw=raw)
