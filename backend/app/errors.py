"""Raw yt-dlp/FFmpeg failures in, machine-readable codes out.

The backend never returns Turkish text. The frontend owns every user-facing string
(`frontend/src/i18n/tr.ts`), so adding a second language is a one-file change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Ordered: the first pattern that matches wins, so put the specific ones first.
_PATTERNS: list[tuple[str, str]] = [
    ("DRM_PROTECTED", r"\bdrm\b|protected by drm|widevine|playready"),
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


@dataclass(slots=True)
class AppError(Exception):
    """An error with a stable code; `raw` is kept so the UI can show the real log."""

    code: str
    raw: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "raw": self.raw, "detail": self.detail}


def classify(message: str) -> str:
    """Map a raw error message onto one of the known codes."""
    text = message.lower()
    for code, pattern in _PATTERNS:
        if re.search(pattern, text):
            return code
    return UNKNOWN


def from_exception(exc: BaseException) -> AppError:
    raw = str(exc) or exc.__class__.__name__
    return AppError(code=classify(raw), raw=raw)
