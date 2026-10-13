"""Does yt-dlp know this site? Answered offline, from the extractors' URL patterns alone.

The Safari extension asks on every page, so this must never touch the network and must be
fast (a few milliseconds after the first call, which compiles the patterns). The generic
extractor matches every URL, so it does not count: an unknown page is "not supported" here,
and the extension falls back to looking for <video>/<audio> elements on the page itself.
"""

from __future__ import annotations

import functools
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app import inspect_service, paths

_LOCK = threading.Lock()


@functools.cache
def _extractors() -> tuple[Any, ...]:
    from yt_dlp.extractor import gen_extractor_classes

    return tuple(c for c in gen_extractor_classes() if c.ie_key() != "Generic")


# yt-dlp's own hint per extractor: "video", "playlist", or "any"/None when it can be either.
_KINDS = {"video": "video", "playlist": "playlist"}
NOT_SUPPORTED = {
    "supported": False,
    "extractor": None,
    "id": None,
    "working": None,
    "kind": None,
}


def supports(url: str) -> dict[str, Any]:
    """`kind` tells the extension what one click can do: a single video downloads; a playlist,
    channel or feed page ("playlist") is opened in the app instead; "unknown" may be either."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return dict(NOT_SUPPORTED)
    # Scheme and host are case-insensitive; yt-dlp's patterns expect them in lower case.
    url = urlunsplit(parts._replace(scheme=parts.scheme.lower(), netloc=parts.netloc.lower()))
    if paths.fixture_mode() and inspect_service.has_fixture(url):
        return {
            **NOT_SUPPORTED,
            "supported": True,
            "extractor": "fixture",
            "working": True,
            "kind": "unknown",
        }
    # yt-dlp compiles each pattern lazily into a class attribute; keep that single-threaded.
    with _LOCK:
        for extractor in _extractors():
            if extractor.suitable(url):
                try:
                    video_id = str(extractor._match_id(url))  # from the URL pattern, offline
                except Exception:
                    video_id = None
                return {
                    "supported": True,
                    "extractor": extractor.ie_key(),
                    "id": video_id,
                    "working": bool(extractor.working()),
                    "kind": _KINDS.get(getattr(extractor, "_RETURN_TYPE", None) or "", "unknown"),
                }
    return dict(NOT_SUPPORTED)
