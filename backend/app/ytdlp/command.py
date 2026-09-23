"""Build the equivalent yt-dlp command line for a selection, for learning and debugging."""

from __future__ import annotations

import shlex
from typing import Any

MODE_SEPARATE = "separate"
MODE_MKV = "mkv"
MODE_COMPAT_MP4 = "compat_mp4"
MODE_AUDIO = "audio"


def build_command(
    url: str,
    *,
    video_format_id: str | None = None,
    audio_format_ids: list[str] | None = None,
    subtitle_keys: list[str] | None = None,
    mode: str = MODE_MKV,
    audio_codec: str | None = None,
    reencode: bool = False,
) -> list[str]:
    """The argv a user could paste into a terminal to reproduce what the UI is about to do."""
    audio_format_ids = audio_format_ids or []
    subtitle_keys = subtitle_keys or []
    argv = ["yt-dlp"]

    selector_parts = [p for p in [video_format_id, *audio_format_ids] if p]
    if selector_parts:
        argv += ["-f", "+".join(selector_parts)]
    if len(audio_format_ids) > 1:
        # Without this, every audio stream after the first is silently dropped.
        argv.append("--audio-multistreams")

    if mode == MODE_MKV:
        argv += ["--merge-output-format", "mkv", "--embed-chapters", "--embed-metadata"]
    elif mode == MODE_COMPAT_MP4:
        argv += ["--merge-output-format", "mp4"]
        if reencode:
            argv += ["--recode-video", "mp4"]
        argv += ["--embed-chapters", "--embed-metadata"]
    elif mode == MODE_AUDIO:
        argv += [
            "-x",
            "--audio-format",
            audio_codec or "mp3",
            "--embed-thumbnail",
            "--embed-metadata",
        ]

    if subtitle_keys:
        argv += ["--write-subs", "--write-auto-subs", "--sub-langs", ",".join(subtitle_keys)]
        if mode not in (MODE_SEPARATE, MODE_AUDIO):
            argv.append("--embed-subs")

    argv.append(url)
    return argv


def inspect_command(url: str) -> list[str]:
    return ["yt-dlp", "-J", "--no-download", "--write-subs", "--write-auto-subs", url]


def quote(argv: list[str]) -> str:
    """Shell-quote for display. Nothing in this app executes a shell string, but Berk will paste
    this into a terminal, so a hostile URL must not be able to break out of its quotes."""
    return shlex.join(argv)


def command_for_model(model: dict[str, Any], url: str) -> list[str]:
    """A sensible default command for an inspected item: best video + its original audio."""
    video = model.get("video_formats") or model.get("muxed_formats") or []
    groups = model.get("audio_languages") or []
    return build_command(
        url,
        video_format_id=video[0]["format_id"] if video else None,
        audio_format_ids=[groups[0]["tracks"][0]["format_id"]] if groups else [],
    )
