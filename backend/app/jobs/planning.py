"""Everything the UI shows before a download starts, and the worker request it turns into."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app import errors, paths
from app.settings import Settings
from app.ytdlp import command, compat, naming, normalize

EXTENSIONS = {"mkv": "mkv", "compat_mp4": "mp4"}


def final_extension(mode: str, audio_codec: str | None, video: dict[str, Any] | None) -> str:
    if mode == "audio":
        return audio_codec or "mp3"
    if mode == "separate":
        return str((video or {}).get("ext") or "mp4")
    return EXTENSIONS[mode]


def plan(entry: dict[str, Any], selection: dict[str, Any], settings: Settings) -> dict[str, Any]:
    model = entry["model"]
    mode = selection["mode"]
    formats = compat.index_formats(model)
    advice = compat.advise(
        model,
        mode=mode,
        video_format_id=selection.get("video_format_id"),
        audio_format_ids=selection.get("audio_format_ids") or [],
        subtitle_keys=selection.get("subtitle_keys") or [],
        audio_codec=selection.get("audio_codec"),
    )
    ids = [
        i
        for i in [selection.get("video_format_id"), *(selection.get("audio_format_ids") or [])]
        if i
    ]
    video = formats.get(selection.get("video_format_id") or "")
    ext = final_extension(mode, selection.get("audio_codec"), video)
    template = selection.get("filename_template") or settings.filename_template
    filename, filename_error = None, None
    try:
        filename = f"{naming.render_relative(template, entry['template_info'], ext)}.{ext}"
    except errors.AppError as exc:
        filename_error = exc.code
    reencode = advice["plan"].get("video") == "transcode"
    argv = command.build_command(
        entry["url"],
        video_format_id=selection.get("video_format_id"),
        audio_format_ids=selection.get("audio_format_ids") or [],
        subtitle_keys=selection.get("subtitle_keys") or [],
        mode=mode,
        audio_codec=selection.get("audio_codec"),
        reencode=reencode,
    )
    return {
        "size": normalize.estimate_total_size(model, ids),
        "notices": advice["notices"],
        "plan": advice["plan"],
        "blocking": advice["blocking"] or filename_error is not None,
        "filename": filename,
        "filename_error": filename_error,
        "download_dir": settings.download_dir,
        "command": command.quote(argv),
    }


def build_job(
    entry: dict[str, Any], selection: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    """Validate a selection and turn it into a stored job with its complete worker request."""
    preview = plan(entry, selection, settings)
    if preview["filename_error"]:
        raise errors.AppError(
            code=preview["filename_error"], raw=str(selection.get("filename_template"))
        )
    if preview["blocking"]:
        codes = [n["code"] for n in preview["notices"] if n["level"] == "error"]
        raise errors.AppError(code="SELECTION_INVALID", raw=", ".join(codes))

    model = entry["model"]
    formats = compat.index_formats(model)
    subtitles = compat.index_subtitles(model)
    job_id = uuid.uuid4().hex[:12]
    root = Path(settings.download_dir).expanduser()
    audio_ids = list(selection.get("audio_format_ids") or [])
    subtitle_keys = list(selection.get("subtitle_keys") or [])
    selected = [i for i in [selection.get("video_format_id"), *audio_ids] if i]
    request = {
        "job_id": job_id,
        "url": entry["url"],
        "mode": selection["mode"],
        "video_format_id": selection.get("video_format_id"),
        "audio_format_ids": audio_ids,
        "subtitle_keys": subtitle_keys,
        "audio_codec": selection.get("audio_codec"),
        "audio_quality": selection.get("audio_quality"),
        "extras": selection.get("extras") or {"thumbnail": True},
        "filename_template": selection.get("filename_template") or settings.filename_template,
        "download_dir": str(root),
        "work_dir": str(root / ".vd-work" / job_id),
        "expected_sizes": {fid: formats[fid].get("filesize") for fid in selected if fid in formats},
        "audio_tracks": [
            {
                "format_id": fid,
                "language": formats[fid].get("language"),
                "role": formats[fid].get("role"),
            }
            for fid in audio_ids
            if fid in formats
        ],
        "subtitle_tracks": [
            {"key": key, "language": subtitles[key]["language"], "kind": subtitles[key]["kind"]}
            for key in subtitle_keys
            if key in subtitles
        ],
        "info": entry.get("fixture_info") if paths.fixture_mode() else None,
        # Only while the setting is on: turning it off stops it for every later job too.
        "cookies_from_browser": entry.get("cookies") if settings.safari_login else None,
    }
    return {
        "id": job_id,
        "kind": "download",
        "status": "queued",
        "stage": "queued",
        "title": model["media"].get("title"),
        "source_url": entry["url"],
        "mode": selection["mode"],
        "request": request,
    }
