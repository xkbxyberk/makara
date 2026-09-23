"""Will the chosen combination play where Berk wants it to, and what will it cost?

Returns machine-readable notices (the frontend words them in Turkish) and the exact
copy-vs-transcode plan the worker will execute, so the UI can state a re-encode *before*
the job starts rather than after.
"""

from __future__ import annotations

from typing import Any

from app.ytdlp.selection import codec_family, is_compatible_audio, is_compatible_video

INFO, WARN, ERROR = "info", "warn", "error"
AUDIO_CODECS = ("mp3", "m4a", "opus", "flac", "wav")
LABELS = {
    "av01": "AV1",
    "vp09": "VP9",
    "vp9": "VP9",
    "avc1": "H.264",
    "avc3": "H.264",
    "hvc1": "HEVC",
    "hev1": "HEVC",
    "opus": "Opus",
    "mp4a": "AAC",
    "vorbis": "Vorbis",
}


def _label(codec: str | None) -> str:
    family = codec_family(codec)
    return LABELS.get(family, family.upper() or "?")


def index_formats(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = [
        *model.get("video_formats", []),
        *model.get("muxed_formats", []),
        *[t for g in model.get("audio_languages", []) for t in g["tracks"]],
    ]
    return {row["format_id"]: row for row in rows}


def index_subtitles(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    subs = model.get("subtitles", {})
    rows = [*subs.get("manual", []), *subs.get("auto", []), *subs.get("auto_translated", [])]
    # Manual wins over an automatic track with the same key, as it does inside yt-dlp.
    out: dict[str, dict[str, Any]] = {}
    for row in reversed(rows):
        out[row["key"]] = row
    return out


def advise(
    model: dict[str, Any],
    *,
    mode: str,
    video_format_id: str | None,
    audio_format_ids: list[str],
    subtitle_keys: list[str],
    audio_codec: str | None = None,
) -> dict[str, Any]:
    formats = index_formats(model)
    subs = index_subtitles(model)
    notices: list[dict[str, Any]] = []

    def note(code: str, level: str, **params: Any) -> None:
        notices.append({"code": code, "level": level, "params": params})

    unknown = [f for f in [video_format_id, *audio_format_ids] if f and f not in formats]
    unknown_subs = [k for k in subtitle_keys if k not in subs]
    if unknown or unknown_subs:
        note("UNKNOWN_SELECTION", ERROR, ids=[*unknown, *unknown_subs])

    video = formats.get(video_format_id or "")
    audios = [formats[a] for a in audio_format_ids if a in formats]
    plan: dict[str, Any] = {"video": None, "audio": [], "subtitles": None}

    if mode == "audio":
        if not audios:
            note("NO_AUDIO_SELECTED", ERROR)
        if audio_codec not in AUDIO_CODECS:
            note("UNKNOWN_AUDIO_CODEC", ERROR, codec=audio_codec)
        if audio_codec == "wav":
            note("WAV_NO_COVER", INFO)
        if len(audios) > 1:
            note("AUDIO_MODE_ONE_TRACK", ERROR)
        if audios and audio_codec in AUDIO_CODECS:
            plan["audio"] = [_audio_extract_step(audios[0], audio_codec, note)]
        return {"notices": notices, "plan": plan, "blocking": _blocking(notices)}

    if video is None:
        note("NO_VIDEO_SELECTED", ERROR)
    elif not audios and not video.get("has_audio"):
        note("SILENT_VIDEO", WARN)

    if any(f.get("drm") == "maybe" for f in [video, *audios] if f):
        note("DRM_MAYBE_SELECTED", WARN)
    if any(subs[k]["kind"] == "auto_translated" for k in subtitle_keys if k in subs):
        note("MACHINE_TRANSLATED_SUBS", INFO)

    if mode == "mkv":
        note("MKV_PLAYERS", INFO)
        if video and codec_family(video.get("vcodec")) == "av01":
            note("AV1_HARDWARE", INFO)
        own_audio = ["copy"] if video and video.get("has_audio") and not audios else []
        plan.update(video="copy", audio=own_audio + ["copy"] * len(audios), subtitles="srt")
    elif mode == "compat_mp4":
        plan["subtitles"] = "mov_text"
        if video:
            if video.get("vcodec") is None:
                # The site did not say. The worker probes the real file and re-encodes only if
                # it has to -- so say "may", never a confident "copy".
                plan["video"] = "probe"
                note("CODEC_UNKNOWN", WARN)
            elif is_compatible_video(video):
                plan["video"] = "copy"
            else:
                plan["video"] = "transcode"
                note("VIDEO_REENCODE", WARN, codec=_label(video.get("vcodec")))
                alternative = _best_compatible_video(model)
                if alternative:
                    note(
                        "COMPATIBLE_ALTERNATIVE",
                        INFO,
                        format_id=alternative["format_id"],
                        height=alternative.get("height"),
                    )
                if video.get("dynamic_range") not in (None, "SDR"):
                    note("HDR_TONEMAP", WARN, range=video.get("dynamic_range"))
        plan["audio"] = []
        # A muxed format's own sound is used when no separate track was chosen.
        sources = audios or ([video] if video and video.get("has_audio") else [])
        for audio in sources:
            if audio.get("acodec") is None:
                plan["audio"].append("probe")
                if not any(n["code"] == "CODEC_UNKNOWN" for n in notices):
                    note("CODEC_UNKNOWN", WARN)
            elif is_compatible_audio(audio):
                plan["audio"].append("copy")
            else:
                plan["audio"].append("transcode")
                note("AUDIO_REENCODE", INFO, codec=_label(audio.get("acodec")))
        if len(audios) > 1:
            note("MP4_MULTI_AUDIO", INFO)
    elif mode == "separate":
        plan.update(video="copy", audio=["copy"] * len(audios))

    return {"notices": notices, "plan": plan, "blocking": _blocking(notices)}


# What yt-dlp's FFmpegExtractAudio copies without re-encoding, per target.
_EXTRACT_COPIES = {"m4a": {"mp4a", "aac"}, "mp3": {"mp3"}, "opus": {"opus"}, "flac": {"flac"}}
_LOSSLESS = {"flac", "alac", "wav", "pcm_s16le"}


def _audio_extract_step(source: dict[str, Any], target: str, note: Any) -> str:
    family = codec_family(source.get("acodec"))
    if not family:
        return "probe"
    if family in _EXTRACT_COPIES.get(target, set()):
        note("AUDIO_MODE_COPY", INFO, codec=_label(source.get("acodec")))
        return "copy"
    if target in ("flac", "wav") and family not in _LOSSLESS:
        note("LOSSLESS_FROM_LOSSY", INFO, codec=_label(source.get("acodec")))
    else:
        note("AUDIO_MODE_REENCODE", INFO, codec=_label(source.get("acodec")), target=target)
    return "transcode"


def _best_compatible_video(model: dict[str, Any]) -> dict[str, Any] | None:
    rows = [f for f in model.get("video_formats", []) if is_compatible_video(f)]
    return max(rows, key=lambda f: (f.get("height") or 0, not f.get("is_manifest")), default=None)


def _blocking(notices: list[dict[str, Any]]) -> bool:
    return any(n["level"] == ERROR for n in notices)
