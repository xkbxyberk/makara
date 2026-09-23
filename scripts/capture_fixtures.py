"""One-off, opt-in script: record real yt-dlp info dicts as test fixtures.

Metadata only -- nothing is ever downloaded. Run with:
    uv run python scripts/capture_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yt_dlp

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "infojson"

# name -> (candidate urls, extra params, predicate the info dict must satisfy)
TARGETS: list[tuple[str, list[str], dict[str, Any], Any]] = [
    (
        "youtube_multi_audio",
        [
            "https://www.youtube.com/watch?v=0e3GPea1Tyg",
            "https://www.youtube.com/watch?v=WcpfjA4KUmU",
            "https://www.youtube.com/watch?v=2isYuQZMbdU",
            "https://www.youtube.com/watch?v=erLbbextvlY",
        ],
        {},
        lambda i: (
            len(
                {
                    f.get("language")
                    for f in i.get("formats", [])
                    if f.get("acodec") not in (None, "none") and f.get("language")
                }
            )
            >= 2
        ),
    ),
    (
        "youtube_many_subs",
        [
            "https://www.youtube.com/watch?v=iG9CE55wbtY",
            "https://www.youtube.com/watch?v=8S0FDjFBj8o",
            "https://www.youtube.com/watch?v=Hr5tyGHNxhU",
        ],
        {"writesubtitles": True, "writeautomaticsub": True},
        lambda i: (
            len(i.get("subtitles") or {}) >= 3 and len(i.get("automatic_captions") or {}) >= 20
        ),
    ),
    (
        "youtube_playlist_flat",
        [
            "https://www.youtube.com/@TED/videos",
            "https://www.youtube.com/@veritasium/videos",
        ],
        {"extract_flat": "in_playlist", "playlistend": 12},
        lambda i: i.get("_type") == "playlist" and len(i.get("entries") or []) >= 5,
    ),
    (
        "other_site",
        [
            "https://archive.org/details/BigBuckBunny_124",
            "https://archive.org/details/Sita_Sings_the_Blues",
            "https://www.dailymotion.com/video/x2hwqn9",
            "https://soundcloud.com/octobersveryown/drake-hold-on-were-going-home",
        ],
        {},
        lambda i: bool(i.get("formats")),
    ),
]

BASE: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "js_runtimes": {"deno": {"path": "/opt/homebrew/bin/deno"}},
}


SUB_QUERY_KEEP = ("lang", "tlang", "kind", "fmt", "v")


def trim_sub_url(url: str) -> str:
    """Keep only the query parameters that identify what a subtitle track actually is."""
    base, _, query = url.partition("?")
    kept = [p for p in query.split("&") if p.split("=")[0] in SUB_QUERY_KEEP]
    return base + ("?" + "&".join(kept) if kept else "")


def shrink(obj: Any, *, ctx: str = "") -> Any:
    """Drop the bulky, normalisation-irrelevant parts (format URLs, fragments, headers)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("http_headers", "fragments", "downloader_options", "_format_sort_fields"):
                continue
            if ctx == "formats" and k == "url":
                out[k] = ""
                continue
            if ctx == "formats" and k == "manifest_url" and isinstance(v, str):
                out[k] = v.split("?")[0]
                continue
            if ctx == "subs" and k == "url" and isinstance(v, str):
                out[k] = trim_sub_url(v)
                continue
            child = ctx
            if k == "formats":
                child = "formats"
            elif k in ("subtitles", "automatic_captions", "requested_subtitles"):
                child = "subs"
            out[k] = shrink(v, ctx=child)
        return out
    if isinstance(obj, list):
        return [shrink(v, ctx=ctx) for v in obj]
    return obj


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[1:])
    failures = []
    for name, urls, extra, ok in TARGETS:
        if wanted and name not in wanted:
            continue
        saved = False
        for url in urls:
            try:
                with yt_dlp.YoutubeDL({**BASE, **extra}) as ydl:
                    raw = ydl.extract_info(url, download=False)
                    info = ydl.sanitize_info(raw)
                if not info or not ok(info):
                    print(f"  {name}: {url} did not satisfy the predicate")
                    continue
            except Exception as exc:  # this is a diagnostic script
                print(f"  {name}: {url} failed: {type(exc).__name__}: {exc}")
                continue
            path = OUT / f"{name}.json"
            path.write_text(json.dumps(shrink(info), ensure_ascii=False, indent=1))
            print(f"OK {name}: {url} -> {path.name} ({path.stat().st_size // 1024} KiB)")
            saved = True
            break
        if not saved:
            failures.append(name)
    if failures:
        print(f"MISSING: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
