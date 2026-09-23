"""Build the FFmpeg command that turns downloaded streams into the final file.

yt-dlp only fetches raw streams; muxing is done here so that language tags, default flags,
subtitle codecs and "copy vs re-encode" are decided explicitly -- by probing the real files --
rather than inherited from whatever yt-dlp's merger happens to do in a given release.
Always an argv list; never a shell string.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COPYABLE_VIDEO_MP4 = {"h264": "avc1", "hevc": "hvc1"}  # codec -> the tag QuickTime insists on
COPYABLE_AUDIO_MP4 = {"aac", "alac", "mp3"}
TEXT_SUBS_KEEP_IN_MKV = {"ass", "ssa", "subrip"}


@dataclass(slots=True)
class MuxInput:
    path: Path
    kind: str  # "video" | "audio" | "subtitle"
    language: str | None = None
    streams: list[dict[str, Any]] = field(default_factory=list)  # from ffprobe


def iso639_2(code: str | None) -> str:
    """Matroska and MP4 language tags are ISO 639-2. YouTube hands us BCP-47 ("en-US")."""
    if not code:
        return "und"
    base = code.split("-")[0].lower()
    if len(base) == 3:
        return base
    from yt_dlp.utils import ISO639Utils

    return ISO639Utils.short2long(base) or "und"


def ffmetadata_chapters(chapters: list[dict[str, Any]]) -> str:
    def esc(text: str) -> str:
        return re.sub(r"([=;#\\\n])", r"\\\1", text)

    lines = [";FFMETADATA1"]
    for chapter in chapters:
        start, end = chapter.get("start_time"), chapter.get("end_time")
        if start is None or end is None or end <= start:
            continue
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(start * 1000)}",
            f"END={int(end * 1000)}",
            f"title={esc(str(chapter.get('title') or ''))}",
        ]
    return "\n".join(lines) + "\n"


def build_mux_argv(
    *,
    container: str,
    inputs: list[MuxInput],
    output: Path,
    thumbnail: Path | None = None,
    chapters_file: Path | None = None,
    metadata: dict[str, str] | None = None,
    aac_encoder: str = "aac",
    separate_audio: bool = True,
) -> tuple[list[str], dict[str, list[str]]]:
    """-> (argv, plan) where plan records what was copied and what was re-encoded."""
    if container not in ("mkv", "mp4"):
        raise ValueError(container)
    argv = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    maps: list[str] = []
    codecs: list[str] = []
    plan: dict[str, list[str]] = {"video": [], "audio": [], "subtitle": []}
    counts = {"v": 0, "a": 0, "s": 0}
    audio_languages: list[str] = []

    for index, item in enumerate(inputs):
        argv += ["-i", str(item.path)]
        for stream in item.streams:
            kind = stream.get("codec_type")
            codec = str(stream.get("codec_name") or "")
            if kind == "video" and item.kind == "video" and counts["v"] == 0:
                if stream.get("disposition", {}).get("attached_pic"):
                    continue
                n = counts["v"]
                maps += ["-map", f"{index}:{stream['index']}"]
                if container == "mp4" and codec not in COPYABLE_VIDEO_MP4:
                    codecs += [
                        f"-c:v:{n}",
                        "libx264",
                        "-crf",
                        "20",
                        "-preset",
                        "veryfast",
                        "-pix_fmt",
                        "yuv420p",
                        f"-tag:v:{n}",
                        "avc1",
                    ]
                    plan["video"].append(f"transcode:{codec}->h264")
                else:
                    codecs += [f"-c:v:{n}", "copy"]
                    if container == "mp4":
                        codecs += [f"-tag:v:{n}", COPYABLE_VIDEO_MP4[codec]]
                    plan["video"].append(f"copy:{codec}")
                counts["v"] += 1
            elif kind == "audio" and (
                item.kind == "audio" or (item.kind == "video" and not separate_audio)
            ):
                # A muxed file's own sound is kept only when no separate track was chosen;
                # otherwise the user's explicit choice would be doubled by a hidden one.
                n = counts["a"]
                maps += ["-map", f"{index}:{stream['index']}"]
                if container == "mp4" and codec not in COPYABLE_AUDIO_MP4:
                    codecs += [f"-c:a:{n}", aac_encoder, f"-b:a:{n}", "192k"]
                    plan["audio"].append(f"transcode:{codec}->aac")
                else:
                    codecs += [f"-c:a:{n}", "copy"]
                    plan["audio"].append(f"copy:{codec}")
                audio_languages.append(iso639_2(item.language))
                counts["a"] += 1
            elif kind == "subtitle" and item.kind == "subtitle":
                n = counts["s"]
                maps += ["-map", f"{index}:{stream['index']}"]
                if container == "mp4":
                    target = "mov_text"
                else:
                    target = "copy" if codec in TEXT_SUBS_KEEP_IN_MKV else "srt"
                codecs += [f"-c:s:{n}", target]
                codecs += [f"-metadata:s:s:{n}", f"language={iso639_2(item.language)}"]
                codecs += [f"-disposition:s:{n}", "0"]
                plan["subtitle"].append(f"{target}:{codec}")
                counts["s"] += 1

    for n, language in enumerate(audio_languages):
        codecs += [f"-metadata:s:a:{n}", f"language={language}"]
        # The first audio track (the original, by construction) is the one players start with.
        codecs += [f"-disposition:a:{n}", "default" if n == 0 else "0"]

    extra_inputs = len(inputs)
    # Global metadata is written explicitly below. "-map_metadata -1" would also strip chapter
    # titles, so when there are chapters the (tag-less) ffmetadata file is the metadata source.
    metadata_source = "-1"
    if chapters_file is not None:
        argv += ["-f", "ffmetadata", "-i", str(chapters_file)]
        codecs += ["-map_chapters", str(extra_inputs)]
        metadata_source = str(extra_inputs)
        extra_inputs += 1
    if thumbnail is not None and container == "mp4":
        argv += ["-i", str(thumbnail)]
        n = counts["v"]
        maps += ["-map", f"{extra_inputs}:0"]
        codecs += [f"-c:v:{n}", "mjpeg", f"-disposition:v:{n}", "attached_pic"]
        extra_inputs += 1
    if thumbnail is not None and container == "mkv":
        codecs += [
            "-attach",
            str(thumbnail),
            "-metadata:s:t:0",
            "mimetype=image/jpeg",
            "-metadata:s:t:0",
            "filename=cover.jpg",
        ]

    meta = ["-map_metadata", metadata_source]
    for key, value in (metadata or {}).items():
        if value:
            meta += ["-metadata", f"{key}={value}"]
    tail = ["-movflags", "+faststart"] if container == "mp4" else []
    argv += maps + codecs + meta + tail + ["-progress", "pipe:1", "-nostats", str(output)]
    return argv, plan


def run_with_progress(
    argv: list[str], duration: float | None, on_progress: Callable[[float], None]
) -> None:
    """Run FFmpeg, reporting 0..1 from its machine-readable `-progress` stream."""
    argv = [shutil.which("ffmpeg") or "ffmpeg", *argv[1:]]
    with tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=stderr, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            # out_time_ms is, despite its name, in microseconds -- same as out_time_us.
            if key in ("out_time_us", "out_time_ms") and duration and value.isdigit():
                on_progress(min(1.0, int(value) / 1_000_000 / duration))
            elif key == "progress" and value == "end":
                on_progress(1.0)
        code = proc.wait()
        if code != 0:
            stderr.seek(0)
            raise RuntimeError(
                f"ffmpeg exited {code}: {stderr.read().decode(errors='replace')[-2000:]}"
            )
