"""The preselected tracks for each output mode -- what "two clicks to download" gives you.

Defaults agreed with Berk: the best video, the ORIGINAL audio only, and human-made Turkish and
English subtitles when they exist. Dubs and auto-captions are always opt-in.
"""

from __future__ import annotations

from typing import Any

DEFAULT_SUBTITLE_LANGUAGES = ("tr", "en")

# Higher is better. Archive prefers efficient codecs; compatibility prefers what Apple plays.
_ARCHIVE_VIDEO = {"av01": 3, "vp09": 2, "vp9": 2, "hev1": 1, "hvc1": 1, "avc1": 1, "avc3": 1}
_COMPAT_VIDEO = {"avc1": 2, "avc3": 2, "h264": 2, "hvc1": 1, "hev1": 1}
_ARCHIVE_AUDIO = {"opus": 2, "mp4a": 1, "aac": 1}
_COMPAT_AUDIO = {"mp4a": 2, "aac": 2}


def codec_family(codec: str | None) -> str:
    return (codec or "").split(".")[0].lower()


def is_compatible_video(fmt: dict[str, Any]) -> bool:
    return codec_family(fmt.get("vcodec")) in _COMPAT_VIDEO


def is_compatible_audio(fmt: dict[str, Any]) -> bool:
    return codec_family(fmt.get("acodec")) in _COMPAT_AUDIO


def _variant_penalty(fmt: dict[str, Any]) -> int:
    """yt-dlp marks YouTube's AI-upscaled (-sr) and dynamic-range-compressed (-drc) variants.
    Neither is the original, so an archive should not pick them when an alternative exists."""
    return 1 if str(fmt["format_id"]).endswith(("-sr", "-drc")) else 0


def pick_video(model: dict[str, Any], mode: str) -> dict[str, Any] | None:
    candidates = [
        f
        for f in [*model.get("video_formats", []), *model.get("muxed_formats", [])]
        if f.get("drm") != "yes"
    ]
    if not candidates:
        return None
    if mode == "compat_mp4":

        def key(f: dict[str, Any]) -> tuple[Any, ...]:
            return (
                is_compatible_video(f),
                -_variant_penalty(f),
                f.get("height") or 0,
                not f.get("is_manifest"),
                f.get("fps") or 0,
                f.get("tbr") or 0,
            )
    else:

        def key(f: dict[str, Any]) -> tuple[Any, ...]:
            # An AI-upscaled 720p is not a better archive than the real 240p it came from.
            return (
                -_variant_penalty(f),
                f.get("height") or 0,
                f.get("fps") or 0,
                not f.get("is_manifest"),
                _ARCHIVE_VIDEO.get(codec_family(f.get("vcodec")), 0),
                f.get("tbr") or 0,
            )

    return max(candidates, key=key)


def pick_audio_track(group: dict[str, Any], mode: str) -> dict[str, Any] | None:
    tracks = [t for t in group.get("tracks", []) if t.get("drm") != "yes"]
    if not tracks:
        return None
    table = _COMPAT_AUDIO if mode == "compat_mp4" else _ARCHIVE_AUDIO
    return max(
        tracks,
        key=lambda t: (
            -_variant_penalty(t),
            not t.get("is_manifest"),
            table.get(codec_family(t.get("acodec")), 0),
            t.get("abr") or t.get("tbr") or 0,
        ),
    )


def primary_audio_group(model: dict[str, Any]) -> dict[str, Any] | None:
    groups = model.get("audio_languages") or []
    for role in ("original", "default"):
        for group in groups:
            if group["role"] == role:
                return group
    return groups[0] if groups else None


def default_subtitles(model: dict[str, Any]) -> list[str]:
    manual = model.get("subtitles", {}).get("manual", [])
    chosen: list[str] = []
    for language in DEFAULT_SUBTITLE_LANGUAGES:
        matches = [row["key"] for row in manual if row["language"].split("-")[0] == language]
        if matches:
            # Prefer the bare code ("en") over regional variants ("en-GB").
            chosen.append(language if language in matches else matches[0])
    return chosen


def default_selection(model: dict[str, Any], mode: str) -> dict[str, Any]:
    group = primary_audio_group(model)
    track = pick_audio_track(group, mode) if group else None
    if mode == "audio":
        source = track
        if source is None:
            # Sites like archive.org only offer audio inside a muxed file; extract from that.
            muxed = pick_video(model, "mkv")
            source = muxed if muxed and muxed.get("has_audio") else None
        return {
            "video_format_id": None,
            "audio_format_ids": [source["format_id"]] if source else [],
            "subtitle_keys": [],
        }
    video = pick_video(model, mode)
    # A muxed format already carries its sound; adding another track would double it.
    wants_audio = track is not None and not (video and video.get("has_audio"))
    return {
        "video_format_id": video["format_id"] if video else None,
        "audio_format_ids": [track["format_id"]] if wants_audio and track else [],
        "subtitle_keys": default_subtitles(model),
    }


def all_defaults(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        mode: default_selection(model, mode) for mode in ("mkv", "compat_mp4", "separate", "audio")
    }
