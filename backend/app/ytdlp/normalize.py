"""Turn a raw yt-dlp info dict into the single model every screen consumes.

This module is where the project's domain knowledge lives, so the rules it encodes are
spelled out here rather than scattered through the UI:

* **Audio roles.** yt-dlp exposes no "is this a dub?" field. The only reliable signal is
  `language_preference`: 10 = original, 5 = the track YouTube defaults to, -10 = audio
  description, anything else = a dub. yt-dlp cannot tell a human dub from an AI auto-dub
  (there is no such field anywhere in the extractor), so neither can we, and we do not
  pretend otherwise -- everything non-original is simply "dub".
* **Subtitles come in three kinds, not two.** `subtitles` holds human-uploaded tracks.
  `automatic_captions` mixes *two* different things: the ASR track for the spoken language
  (its key has an `-orig` twin, or its URL carries `kind=asr`) and hundreds of machine
  translations (URL carries `tlang=`, or the display name reads "X from Y").
* **Sizes have three tiers**: exact `filesize`, `filesize_approx`, or `tbr * duration`.
  For HLS/DASH formats `tbr` is often the *peak* rather than the average bitrate, so an
  estimate derived from a manifest format is flagged separately and reads high.
* **`vcodec`/`acodec` use the string `"none"` as a sentinel.** `None` means "unknown",
  which is a different thing -- archive.org returns exactly that.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

BITS_PER_KBIT_OVER_BYTE = 125  # tbr is in kbps (1000 bit/s); /8 gives bytes per second

SIZE_EXACT = "exact"
SIZE_APPROX = "approx"
SIZE_ESTIMATED = "estimated"
SIZE_UNKNOWN = "unknown"

ROLE_ORDER = {"original": 0, "default": 1, "dub": 2, "descriptive": 3, "unknown": 4}
SUB_EXT_PREFERENCE = ("srt", "vtt", "ass", "ttml", "json3", "srv3", "srv2", "srv1")


def _size_of(fmt: dict[str, Any], duration: float | None) -> tuple[int | None, str]:
    if fmt.get("filesize"):
        return int(fmt["filesize"]), SIZE_EXACT
    if fmt.get("filesize_approx"):
        return int(fmt["filesize_approx"]), SIZE_APPROX
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(duration * float(tbr) * BITS_PER_KBIT_OVER_BYTE), SIZE_ESTIMATED
    return None, SIZE_UNKNOWN


def _drm_state(fmt: dict[str, Any]) -> str:
    drm = fmt.get("has_drm")
    if drm == "maybe":
        return "maybe"
    return "yes" if drm else "none"


def format_kind(fmt: dict[str, Any]) -> str:
    """One of: video, audio, muxed, storyboard."""
    vcodec, acodec = fmt.get("vcodec"), fmt.get("acodec")
    has_geometry = bool(fmt.get("height") or fmt.get("width"))
    if fmt.get("ext") == "mhtml" or fmt.get("resolution") == "images":
        return "storyboard"
    if vcodec == "none" and acodec == "none":
        return "storyboard"
    if vcodec == "none":
        return "audio"
    if acodec == "none":
        return "video"
    if vcodec is None:
        # Nothing known about the picture: only a resolution tells us there is one.
        return "muxed" if has_geometry else "audio"
    if acodec is None:
        # A known picture codec with an *unknown* sound: do not claim it carries audio.
        return "video"
    return "muxed"


def audio_role(fmt: dict[str, Any]) -> str:
    language = fmt.get("language") or ""
    preference = fmt.get("language_preference")
    if preference == -10 or language.endswith("-desc"):
        return "descriptive"
    if preference == 10:
        return "original"
    if preference == 5:
        return "default"
    if preference is None:
        return "unknown"
    return "dub"


def _short_codec(codec: str | None) -> str | None:
    """ "avc1.640028" -> "H.264". Keeps the technical string available separately."""
    if not codec or codec == "none":
        return None
    head = codec.split(".")[0].lower()
    table = {
        "avc1": "H.264",
        "avc3": "H.264",
        "h264": "H.264",
        "hev1": "HEVC",
        "hvc1": "HEVC",
        "h265": "HEVC",
        "dvh1": "Dolby Vision",
        "dvhe": "Dolby Vision",
        "av01": "AV1",
        "vp09": "VP9",
        "vp9": "VP9",
        "vp8": "VP8",
        "mp4a": "AAC",
        "aac": "AAC",
        "opus": "Opus",
        "vorbis": "Vorbis",
        "mp3": "MP3",
        "flac": "FLAC",
        "alac": "ALAC",
        "ec-3": "E-AC-3",
        "ac-3": "AC-3",
    }
    return table.get(head, codec.split(".")[0].upper())


def _common_format_fields(fmt: dict[str, Any], duration: float | None) -> dict[str, Any]:
    size, size_kind = _size_of(fmt, duration)
    is_manifest = bool(fmt.get("manifest_url")) or str(fmt.get("protocol", "")).startswith(
        ("m3u8", "http_dash")
    )
    return {
        "format_id": str(fmt.get("format_id") or ""),
        "ext": fmt.get("ext"),
        "container": fmt.get("container"),
        "protocol": fmt.get("protocol"),
        "is_manifest": is_manifest,
        "filesize": size,
        "filesize_kind": size_kind,
        # A tbr-derived estimate off a manifest format reads high; say so rather than lie.
        "filesize_unreliable": size_kind == SIZE_ESTIMATED and is_manifest,
        "tbr": fmt.get("tbr"),
        "drm": _drm_state(fmt),
        "format_note": fmt.get("format_note"),
        # yt-dlp suffixes YouTube's AI-upscaled video "-sr" and compressed-dynamics audio "-drc".
        "ai_upscaled": str(fmt.get("format_id", "")).endswith("-sr")
        or "AI-upscaled" in str(fmt.get("format_note") or ""),
        "drc": str(fmt.get("format_id", "")).endswith("-drc")
        or "DRC" in str(fmt.get("format_note") or "").split(", "),
    }


def normalize_video_format(fmt: dict[str, Any], duration: float | None) -> dict[str, Any]:
    out = _common_format_fields(fmt, duration)
    out.update(
        {
            "width": fmt.get("width"),
            "height": fmt.get("height"),
            "resolution": fmt.get("resolution"),
            "fps": fmt.get("fps"),
            "vcodec": fmt.get("vcodec"),
            "vcodec_label": _short_codec(fmt.get("vcodec")),
            "vbr": fmt.get("vbr"),
            "dynamic_range": fmt.get("dynamic_range"),
            # True: carries sound. False: known silent. None: unknown (acodec was None).
            "has_audio": True
            if format_kind(fmt) == "muxed"
            else (None if fmt.get("acodec") is None else False),
            "acodec_label": _short_codec(fmt.get("acodec")),
        }
    )
    return out


def normalize_audio_format(fmt: dict[str, Any], duration: float | None) -> dict[str, Any]:
    out = _common_format_fields(fmt, duration)
    out.update(
        {
            "language": fmt.get("language"),
            "language_preference": fmt.get("language_preference"),
            "role": audio_role(fmt),
            "acodec": fmt.get("acodec"),
            "acodec_label": _short_codec(fmt.get("acodec")),
            "abr": fmt.get("abr"),
            "asr": fmt.get("asr"),
            "channels": fmt.get("audio_channels"),
        }
    )
    return out


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def _sub_exts(entries: list[dict[str, Any]]) -> list[str]:
    seen = {e.get("ext") for e in entries if e.get("ext")}
    ordered = [e for e in SUB_EXT_PREFERENCE if e in seen]
    return ordered + sorted(str(e) for e in seen if e not in SUB_EXT_PREFERENCE)


def _sub_name(entries: list[dict[str, Any]]) -> str | None:
    return next((e.get("name") for e in entries if e.get("name")), None)


def classify_automatic_caption(
    key: str, entries: list[dict[str, Any]]
) -> tuple[str, str, str | None]:
    """-> (kind, display language, source language).

    `kind` is "auto" for the ASR track in the spoken language, "auto_translated" for a
    machine translation of some other track.
    """
    name = _sub_name(entries) or ""
    urls = [str(e.get("url") or "") for e in entries]
    if key.endswith("-orig"):
        return "auto", key[: -len("-orig")], None
    for url in urls:
        query = _query(url)
        if query.get("tlang"):
            source = query.get("lang")
            return "auto_translated", key, source[0] if source else None
    if " from " in name:
        # e.g. "Afrikaans from Afrikaans" -- a degenerate same-language translation.
        return "auto_translated", key, key.rsplit("-", 1)[-1]
    return "auto", key, None


def spoken_language(info: dict[str, Any]) -> str | None:
    """The language the ASR track is in. YouTube flags it with an "-orig" twin key."""
    for key in info.get("automatic_captions") or {}:
        if key.endswith("-orig"):
            return key[: -len("-orig")]
    language = info.get("language")
    return str(language) if language else None


def _source_language(key: str, entries: list[dict[str, Any]]) -> str | None:
    for entry in entries:
        query = _query(str(entry.get("url") or ""))
        if query.get("tlang") and query.get("lang"):
            return query["lang"][0]
    name = _sub_name(entries) or ""
    return key.rsplit("-", 1)[-1] if " from " in name and "-" in key else None


def normalize_subtitles(info: dict[str, Any]) -> dict[str, Any]:
    manual: list[dict[str, Any]] = []
    auto: list[dict[str, Any]] = []
    translated: list[dict[str, Any]] = []
    has_live_chat = False

    for key, entries in (info.get("subtitles") or {}).items():
        if key == "live_chat":
            has_live_chat = True
            continue
        if not entries:
            continue
        manual.append(
            {
                "key": key,
                "language": key,
                "name": _sub_name(entries),
                "exts": _sub_exts(entries),
                "kind": "manual",
                "source_language": None,
            }
        )

    spoken = spoken_language(info)
    manual_keys = {row["key"] for row in manual}
    for key, entries in (info.get("automatic_captions") or {}).items():
        if not entries:
            continue
        if spoken is not None:
            # Speech recognition only ever produces the spoken language. Some translations arrive
            # as bare HLS playlists with neither `tlang=` nor a name, so URL sniffing alone would
            # misfile them as auto-generated; knowing the spoken language settles it.
            if key in (spoken, f"{spoken}-orig"):
                kind, language, source = "auto", spoken, None
            else:
                kind, language, source = "auto_translated", key, _source_language(key, entries)
        else:
            kind, language, source = classify_automatic_caption(key, entries)
        row = {
            "key": key,
            "language": language,
            "name": _sub_name(entries),
            "exts": _sub_exts(entries),
            "kind": kind,
            "source_language": source,
            "is_original_track": key.endswith("-orig"),
            # yt-dlp resolves a key to the manual track when both exist, so this row cannot be
            # downloaded as-is; the UI shows it but does not offer it.
            "shadowed_by_manual": key in manual_keys,
        }
        (auto if kind == "auto" else translated).append(row)

    manual.sort(key=lambda r: str(r["language"]))
    auto.sort(key=lambda r: (not r.get("is_original_track"), str(r["language"])))
    translated.sort(key=lambda r: str(r["key"]))
    return {
        "manual": manual,
        "auto": auto,
        "auto_translated": translated,
        "has_live_chat": has_live_chat,
    }


def _thumbnails(info: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows = []
    for thumb in info.get("thumbnails") or []:
        url = thumb.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "id": thumb.get("id"),
                "url": url,
                "width": thumb.get("width"),
                "height": thumb.get("height"),
                "preference": thumb.get("preference"),
            }
        )
    rows.sort(key=lambda t: (-(t["width"] or 0), -(t["height"] or 0)))
    return rows


def _media_meta(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "description": info.get("description"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "upload_date": info.get("upload_date"),
        "timestamp": info.get("timestamp") or info.get("release_timestamp"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "live_status": info.get("live_status"),
        "availability": info.get("availability"),
        "age_limit": info.get("age_limit"),
        "language": info.get("language"),
        "thumbnail": info.get("thumbnail"),
    }


def normalize(info: dict[str, Any]) -> dict[str, Any]:
    """Raw info dict -> the model the API serves and the UI renders."""
    if info.get("_type") in ("playlist", "multi_video"):
        return _normalize_playlist(info)

    duration = info.get("duration")
    formats = info.get("formats") or []
    video_formats, audio_formats, muxed_formats = [], [], []
    for fmt in formats:
        kind = format_kind(fmt)
        if kind == "storyboard":
            continue
        if kind == "audio":
            audio_formats.append(normalize_audio_format(fmt, duration))
        elif kind == "video":
            video_formats.append(normalize_video_format(fmt, duration))
        else:
            muxed_formats.append(normalize_video_format(fmt, duration))

    video_formats.sort(key=lambda f: (-(f["height"] or 0), -(f["fps"] or 0), -(f["tbr"] or 0)))
    muxed_formats.sort(key=lambda f: (-(f["height"] or 0), -(f["tbr"] or 0)))

    groups: dict[str, dict[str, Any]] = {}
    for track in audio_formats:
        key = track["language"] or "und"
        group = groups.setdefault(
            key, {"language": track["language"], "role": track["role"], "tracks": []}
        )
        # The strongest role wins for the group label (original beats dub).
        if ROLE_ORDER[track["role"]] < ROLE_ORDER[group["role"]]:
            group["role"] = track["role"]
        group["tracks"].append(track)
    for group in groups.values():
        group["tracks"].sort(key=lambda t: -(t["abr"] or t["tbr"] or 0))
    audio_languages = sorted(
        groups.values(), key=lambda g: (ROLE_ORDER[g["role"]], str(g["language"] or "zzz"))
    )
    # yt-dlp leaves language_preference at -1 on single-language videos, which would make the
    # only audio track read as a "dub". With nothing to contrast against, say nothing instead.
    if len(audio_languages) == 1 and audio_languages[0]["role"] == "dub":
        audio_languages[0]["role"] = "unknown"
        for track in audio_languages[0]["tracks"]:
            track["role"] = "unknown"

    warnings: list[str] = []
    if info.get("_has_drm"):
        warnings.append("DRM_PRESENT")
    elif any(f["drm"] == "maybe" for f in [*video_formats, *audio_formats, *muxed_formats]):
        warnings.append("DRM_MAYBE")
    if video_formats and all(f["filesize_kind"] != SIZE_EXACT for f in video_formats):
        warnings.append("SIZES_ARE_ESTIMATES")
    if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        warnings.append("LIVE_CONTENT")

    return {
        "kind": "video",
        "media": _media_meta(info),
        "video_formats": video_formats,
        "muxed_formats": muxed_formats,
        "audio_languages": audio_languages,
        "subtitles": normalize_subtitles(info),
        "chapters": [
            {
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time"),
                "title": c.get("title"),
            }
            for c in (info.get("chapters") or [])
        ],
        "heatmap": [
            {
                "start_time": h.get("start_time"),
                "end_time": h.get("end_time"),
                "value": h.get("value"),
            }
            for h in (info.get("heatmap") or [])
        ],
        "thumbnails": _thumbnails(info),
        "warnings": warnings,
    }


def _normalize_playlist(info: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        entries.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "url": entry.get("url") or entry.get("webpage_url"),
                "duration": entry.get("duration"),
                "timestamp": entry.get("timestamp") or entry.get("release_timestamp"),
                "live_status": entry.get("live_status"),
                "view_count": entry.get("view_count") or entry.get("concurrent_view_count"),
                "thumbnail": next(
                    (t.get("url") for t in reversed(entry.get("thumbnails") or []) if t.get("url")),
                    None,
                ),
            }
        )
    return {
        "kind": "playlist",
        "media": {
            "id": info.get("id"),
            "title": info.get("title"),
            "webpage_url": info.get("webpage_url"),
            "extractor": info.get("extractor_key") or info.get("extractor"),
            "channel": info.get("channel") or info.get("uploader"),
            "channel_url": info.get("channel_url") or info.get("uploader_url"),
            "description": info.get("description"),
        },
        "entries": entries,
        "entry_count": info.get("playlist_count") or len(entries),
        "warnings": ["PLAYLIST_TRACKS_NEED_PER_VIDEO_INSPECT"],
    }


def estimate_total_size(model: dict[str, Any], format_ids: list[str]) -> dict[str, Any]:
    """Sum the selected tracks, the way yt-dlp sums a merged output.

    `kind` is the weakest confidence among the parts. If any selected part has no size at all,
    the total is only a lower bound: `kind` becomes "partial" and `missing` counts the gaps.
    """
    wanted = set(format_ids)
    rows = [
        *(model.get("video_formats") or []),
        *(model.get("muxed_formats") or []),
        *[t for g in (model.get("audio_languages") or []) for t in (g.get("tracks") or [])],
    ]
    total, kinds, unreliable, missing = 0, set(), False, 0
    for row in rows:
        if row.get("format_id") not in wanted:
            continue
        wanted.discard(row["format_id"])
        if row.get("filesize"):
            total += int(row["filesize"])
            kinds.add(row.get("filesize_kind") or SIZE_UNKNOWN)
            unreliable = unreliable or bool(row.get("filesize_unreliable"))
        else:
            missing += 1
    missing += len(wanted)  # ids that are not in the model at all
    if not kinds:
        return {"bytes": None, "kind": SIZE_UNKNOWN, "unreliable": False, "missing": missing}
    if missing:
        kind = "partial"
    elif kinds == {SIZE_EXACT}:
        kind = SIZE_EXACT
    elif SIZE_ESTIMATED in kinds:
        kind = SIZE_ESTIMATED
    else:
        kind = SIZE_APPROX
    return {"bytes": total, "kind": kind, "unreliable": unreliable, "missing": missing}
