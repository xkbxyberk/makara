"""Studio operations as data: each becomes a list of steps (FFmpeg argv or a Python action).

The same plan is shown to Berk before a run ("the exact FFmpeg command") and executed by the
studio worker, so what is previewed is what runs. Pure functions; nothing here touches disk
except `probe_source` / `keyframes_near`, which only read.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import errors
from app.ffmpeg.mux import iso639_2

INFO, WARN, ERROR = "info", "warn", "error"
AUDIO_TARGETS = {
    "mp3": ("libmp3lame", "mp3"),
    "m4a": ("aac", "m4a"),
    "opus": ("libopus", "opus"),
    "flac": ("flac", "flac"),
    "wav": ("pcm_s16le", "wav"),
}
LOSSY_AUDIO = {"mp3", "m4a", "opus"}
SUBTITLE_FORMATS = {"srt": "srt", "vtt": "webvtt", "ass": "ass"}
TEXT_SUBTITLE_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}
# What the MP4/MOV muxer takes as a stream copy; anything else is refused with a clear notice.
MP4_COPY = {
    "video": {"h264", "hevc", "av1", "vp9", "mpeg4", "mjpeg", "prores"},
    "audio": {"aac", "mp3", "alac", "opus", "flac", "ac3", "eac3"},
}
LOUDNESS_TARGET = {"I": -16.0, "TP": -1.5, "LRA": 11.0}  # EBU R128 values used by podcasts


@dataclass(slots=True)
class Step:
    kind: str  # "ffmpeg" | "python"
    argv: list[str] = field(default_factory=list)
    action: str = ""  # for python steps: a code the UI words in Turkish
    duration: float | None = None  # media seconds this step processes, for progress
    weight: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "argv": self.argv,
            "action": self.action,
            "duration": self.duration,
            "weight": self.weight,
        }


@dataclass(slots=True)
class Plan:
    steps: list[Step]
    ext: str
    notices: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(n["level"] == ERROR for n in self.notices)

    def note(self, code: str, level: str, **params: Any) -> None:
        self.notices.append({"code": code, "level": level, "params": params})


def _ffmpeg() -> list[str]:
    return [
        shutil.which("ffmpeg") or "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
    ]


def _progress(output: str) -> list[str]:
    return ["-progress", "pipe:1", "-nostats", output]


# ---- reading the source ------------------------------------------------------------------
def probe_source(path: Path) -> dict[str, Any]:
    """Streams, duration and chapters of a user-chosen file. Refuses anything not media."""
    if not path.is_absolute() or not path.is_file():
        raise errors.AppError(code="SOURCE_NOT_FOUND", raw=str(path))
    argv = [
        shutil.which("ffprobe") or "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-show_chapters",
        str(path),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    data = json.loads(proc.stdout or "{}") if proc.returncode == 0 else {}
    streams = data.get("streams") or []
    if not streams:
        raise errors.AppError(code="SOURCE_NOT_MEDIA", raw=proc.stderr[-2000:])
    duration = data.get("format", {}).get("duration")
    return {
        "path": str(path),
        "name": path.name,
        "ext": path.suffix.lstrip(".").lower(),
        "size": path.stat().st_size,
        "duration": float(duration) if duration else None,
        "streams": [
            {
                "index": s.get("index"),
                "type": s.get("codec_type"),
                "codec": s.get("codec_name"),
                "language": (s.get("tags") or {}).get("language"),
                "title": (s.get("tags") or {}).get("title"),
                "default": bool((s.get("disposition") or {}).get("default")),
                "attached_pic": bool((s.get("disposition") or {}).get("attached_pic")),
                "width": s.get("width"),
                "height": s.get("height"),
                "channels": s.get("channels"),
                "sample_rate": s.get("sample_rate"),
            }
            for s in streams
        ],
        "chapters": [
            {
                "start": float(c["start_time"]),
                "end": float(c["end_time"]),
                "title": (c.get("tags") or {}).get("title"),
            }
            for c in data.get("chapters") or []
        ],
    }


def keyframe_at_or_before(path: Path, seconds: float) -> float | None:
    """Where a stream-copy cut requested at `seconds` will really start: the last video
    keyframe at or before it. Reads only a small window of the file."""
    if seconds <= 0:
        return 0.0
    window = f"{max(0.0, seconds - 20):.3f}%{seconds + 0.05:.3f}"
    argv = [
        shutil.which("ffprobe") or "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-skip_frame",
        "nokey",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        "-read_intervals",
        window,
        str(path),
    ]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    times = [float(t) for t in out.split() if t.replace(".", "", 1).isdigit()]
    before = [t for t in times if t <= seconds + 1e-3]
    return max(before) if before else None


# ---- audio: convert / extract / loudness -----------------------------------------------------
def audio_encoder_args(codec: str, bitrate: str | None, aac_encoder: str = "aac") -> list[str]:
    encoder = aac_encoder if codec == "m4a" else AUDIO_TARGETS[codec][0]
    args = ["-c:a", encoder]
    if codec in LOSSY_AUDIO and bitrate:
        args += ["-b:a", f"{int(bitrate)}k"]
    return args


def loudnorm_filter(measured: dict[str, Any] | None = None) -> str:
    base = (
        f"loudnorm=I={LOUDNESS_TARGET['I']}:TP={LOUDNESS_TARGET['TP']}:LRA={LOUDNESS_TARGET['LRA']}"
    )
    if measured is None:
        return base + ":print_format=json"
    return (
        f"{base}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def plan_audio(
    source: dict[str, Any], options: dict[str, Any], output: str, aac_encoder: str = "aac"
) -> Plan:
    codec = options.get("codec") or "mp3"
    if codec not in AUDIO_TARGETS:
        raise errors.AppError(code="UNKNOWN_AUDIO_CODEC", raw=codec)
    audio = [s for s in source["streams"] if s["type"] == "audio"]
    plan = Plan(steps=[], ext=AUDIO_TARGETS[codec][1])
    if not audio:
        plan.note("NO_AUDIO_IN_SOURCE", ERROR)
        return plan
    pick = int(options.get("audio_index") or 0)
    if pick >= len(audio):
        pick = 0
    duration = source.get("duration")
    covers = [s for s in source["streams"] if s["attached_pic"]]
    keep_cover = bool(covers) and codec in ("mp3", "m4a", "flac")
    maps = ["-map", f"0:a:{pick}"]
    extra: list[str] = []
    if keep_cover:
        maps += ["-map", f"0:{covers[0]['index']}"]
        extra += ["-c:v", "copy", "-disposition:v:0", "attached_pic"]
    rate: list[str] = []
    if options.get("sample_rate"):
        rate = ["-ar", str(int(options["sample_rate"]))]
    elif options.get("loudnorm"):
        # loudnorm resamples to 192 kHz internally; pin a normal rate for the output.
        rate = ["-ar", "48000" if codec == "opus" else "44100"]
    channels = ["-ac", str(int(options["channels"]))] if options.get("channels") else []
    encode = audio_encoder_args(codec, options.get("bitrate"), aac_encoder)
    if options.get("loudnorm"):
        # Two passes: measure, then correct linearly -- the accurate way to hit -16 LUFS.
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    # loudnorm prints its measurement at "info" level, on stderr.
                    "-loglevel",
                    "info",
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    "-i",
                    source["path"],
                    "-map",
                    f"0:a:{pick}",
                    "-af",
                    loudnorm_filter(),
                    "-f",
                    "null",
                    "-",
                ],
                action="LOUDNESS_MEASURE",
                duration=duration,
                weight=1.0,
            )
        )
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-i",
                    source["path"],
                    *maps,
                    "-af",
                    "{LOUDNORM_MEASURED}",
                    *encode,
                    *rate,
                    *channels,
                    *extra,
                    "-map_metadata",
                    "0",
                    *_progress(output),
                ],
                action="LOUDNESS_APPLY",
                duration=duration,
                weight=1.0,
            )
        )
        plan.note("LOUDNESS_TWO_PASS", INFO, target=LOUDNESS_TARGET["I"])
    else:
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-i",
                    source["path"],
                    *maps,
                    *encode,
                    *rate,
                    *channels,
                    *extra,
                    "-map_metadata",
                    "0",
                    *_progress(output),
                ],
                duration=duration,
            )
        )
    source_codec = audio[pick]["codec"]
    if codec in ("flac", "wav") and source_codec not in ("flac", "alac", "pcm_s16le", "pcm_s24le"):
        plan.note("LOSSLESS_FROM_LOSSY", INFO, codec=source_codec)
    return plan


# ---- trim / cut / join --------------------------------------------------------------------
def _validate_segments(
    source: dict[str, Any], segments: list[dict[str, Any]], plan: Plan
) -> list[tuple[float, float]]:
    duration = source.get("duration") or 0
    clean: list[tuple[float, float]] = []
    for seg in segments:
        start, end = float(seg.get("start") or 0), float(seg.get("end") or 0)
        if start < 0 or end <= start or (duration and start >= duration):
            plan.note("INVALID_SEGMENT", ERROR, start=start, end=end)
            continue
        clean.append((start, min(end, duration) if duration else end))
    if not clean and not any(n["code"] == "INVALID_SEGMENT" for n in plan.notices):
        plan.note("NO_SEGMENTS", ERROR)
    return clean


def trim_output_ext(source: dict[str, Any], mode: str) -> str:
    ext = source["ext"]
    if mode == "lossless":
        return ext
    has_video = any(s["type"] == "video" and not s["attached_pic"] for s in source["streams"])
    if not has_video:
        return "m4a"
    return "mp4" if ext in ("mp4", "m4v", "mov") else "mkv"


def plan_trim(
    source: dict[str, Any],
    options: dict[str, Any],
    output: str,
    work: str,
    keyframes: dict[float, float | None] | None = None,
) -> Plan:
    mode = options.get("mode") or "lossless"
    join = bool(options.get("join"))
    ext = trim_output_ext(source, mode)
    plan = Plan(steps=[], ext=ext)
    segments = _validate_segments(source, options.get("segments") or [], plan)
    if not segments:
        return plan
    if len(segments) > 1 and not join:
        plan.note("SEGMENTS_SEPARATE", INFO, count=len(segments))
    has_video = any(s["type"] == "video" and not s["attached_pic"] for s in source["streams"])
    has_audio = any(s["type"] == "audio" for s in source["streams"])

    if mode == "lossless":
        plan.note("LOSSLESS_KEYFRAMES", INFO)
        for start, _ in segments:
            actual = (keyframes or {}).get(start)
            if actual is not None and start - actual > 0.05:
                plan.note("CUT_MOVES_TO_KEYFRAME", WARN, requested=start, actual=round(actual, 3))
        pieces = []
        for n, (start, end) in enumerate(segments):
            target = (
                f"{work}/segment_{n}.{ext}"
                if (join and len(segments) > 1)
                else (output if len(segments) == 1 else output.replace("{N}", str(n + 1)))
            )
            pieces.append(target)
            plan.steps.append(
                Step(
                    "ffmpeg",
                    [
                        *_ffmpeg(),
                        "-ss",
                        f"{start:.3f}",
                        "-to",
                        f"{end:.3f}",
                        "-i",
                        source["path"],
                        "-map",
                        "0",
                        "-c",
                        "copy",
                        "-avoid_negative_ts",
                        "make_zero",
                        *_progress(target),
                    ],
                    duration=end - start,
                )
            )
        if join and len(segments) > 1:
            listing = f"{work}/segments.txt"
            plan.steps.append(
                Step("python", action="WRITE_CONCAT_LIST", argv=[listing, *pieces], weight=0.0)
            )
            plan.steps.append(
                Step(
                    "ffmpeg",
                    [
                        *_ffmpeg(),
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        listing,
                        "-map",
                        "0",
                        "-c",
                        "copy",
                        *_progress(output),
                    ],
                    duration=sum(e - s for s, e in segments),
                )
            )
        return plan

    # Frame-accurate: re-encode. H.264/AAC plays everywhere; CRF 18 is visually lossless.
    plan.note("ACCURATE_REENCODES", INFO)
    video_enc = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    audio_enc = ["-c:a", "aac", "-b:a", "192k"]
    if join and len(segments) > 1:
        plan.note("JOIN_FIRST_TRACKS_ONLY", INFO)
        parts, labels = [], []
        for n, (start, end) in enumerate(segments):
            if has_video:
                parts.append(
                    f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{n}]"
                )
                labels.append(f"[v{n}]")
            if has_audio:
                parts.append(
                    f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{n}]"
                )
                labels.append(f"[a{n}]")
        concat = f"{''.join(labels)}concat=n={len(segments)}:v={int(has_video)}:a={int(has_audio)}"
        outs = (["[v]"] if has_video else []) + (["[a]"] if has_audio else [])
        graph = ";".join([*parts, concat + "".join(outs)])
        maps = [x for label in outs for x in ("-map", label)]
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-i",
                    source["path"],
                    "-filter_complex",
                    graph,
                    *maps,
                    *(video_enc if has_video else []),
                    *(audio_enc if has_audio else []),
                    *_progress(output),
                ],
                duration=sum(e - s for s, e in segments),
            )
        )
        return plan
    for n, (start, end) in enumerate(segments):
        target = output if len(segments) == 1 else output.replace("{N}", str(n + 1))
        subs = ["-map", "0:s?", "-c:s", "mov_text" if ext == "mp4" else "copy"]
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-ss",
                    f"{start:.3f}",
                    "-i",
                    source["path"],
                    "-t",
                    f"{end - start:.3f}",
                    *(["-map", "0:v:0"] if has_video else []),
                    "-map",
                    "0:a?",
                    *subs,
                    *(video_enc if has_video else []),
                    *audio_enc,
                    *_progress(target),
                ],
                duration=end - start,
            )
        )
    return plan


# ---- remux + track editor ---------------------------------------------------------------------
def plan_remux(
    source: dict[str, Any],
    options: dict[str, Any],
    output: str,
    extras: list[dict[str, Any]] | None = None,
) -> Plan:
    """Change container and edit tracks without re-encoding (subtitles may be converted)."""
    container = options.get("container") or "mkv"
    if container not in ("mkv", "mp4", "mov"):
        raise errors.AppError(code="UNKNOWN_CONTAINER", raw=container)
    plan = Plan(steps=[], ext=container)
    extras = extras or []
    inputs = [source, *extras]
    tracks = options.get("tracks") or [
        {
            "input": 0,
            "stream": s["index"],
            "keep": True,
            "language": s.get("language"),
            "default": s.get("default"),
            "title": s.get("title"),
        }
        for s in source["streams"]
    ]
    argv = [*_ffmpeg()]
    for item in inputs:
        argv += ["-i", item["path"]]
    maps: list[str] = []
    per_stream: list[str] = []
    counts = {"video": 0, "audio": 0, "subtitle": 0}
    short = {"video": "v", "audio": "a", "subtitle": "s"}
    kept = 0
    for track in tracks:
        if not track.get("keep", True):
            continue
        index = int(track.get("input") or 0)
        if index >= len(inputs):
            plan.note("UNKNOWN_TRACK", ERROR)
            continue
        stream = next(
            (s for s in inputs[index]["streams"] if s["index"] == track.get("stream")), None
        )
        if stream is None or stream["type"] not in counts:
            continue  # data/attachment streams are not offered in the editor
        kind, codec = stream["type"], stream["codec"]
        n = counts[kind]
        spec = f"{short[kind]}:{n}"
        maps += ["-map", f"{index}:{stream['index']}"]
        if container != "mkv" and kind == "subtitle":
            if codec in TEXT_SUBTITLE_CODECS:
                per_stream += [f"-c:{spec}", "mov_text"]
            else:
                plan.note("SUBTITLE_NOT_IN_MP4", ERROR, codec=codec)
        elif (
            container != "mkv"
            and codec not in MP4_COPY.get(kind, set())
            and not stream["attached_pic"]
        ):
            plan.note("CODEC_NOT_IN_MP4", ERROR, codec=codec, kind=kind)
        else:
            per_stream += [f"-c:{spec}", "copy"]
        language = track.get("language")
        if language:
            per_stream += [f"-metadata:s:{spec}", f"language={iso639_2(str(language))}"]
        if track.get("title") is not None:
            per_stream += [f"-metadata:s:{spec}", f"title={track['title']}"]
        if stream["attached_pic"]:
            per_stream += [f"-disposition:{spec}", "attached_pic"]
        else:
            per_stream += [f"-disposition:{spec}", "default" if track.get("default") else "0"]
        counts[kind] += 1
        kept += 1
    if kept == 0:
        plan.note("NO_TRACKS_KEPT", ERROR)
    tail = ["-movflags", "+faststart"] if container in ("mp4", "mov") else []
    plan.steps.append(
        Step(
            "ffmpeg",
            [*argv, *maps, *per_stream, "-map_chapters", "0", *tail, *_progress(output)],
            duration=source.get("duration"),
        )
    )
    plan.note("REMUX_NO_REENCODE", INFO)
    return plan


# ---- subtitle files ----------------------------------------------------------------------------
def plan_subtitle(source: dict[str, Any], options: dict[str, Any], output: str, work: str) -> Plan:
    action = options.get("action") or "convert"
    target = options.get("target") or "srt"
    if target not in SUBTITLE_FORMATS:
        raise errors.AppError(code="UNKNOWN_SUBTITLE_FORMAT", raw=target)
    plan = Plan(steps=[], ext=target)
    if not any(s["type"] == "subtitle" for s in source["streams"]):
        plan.note("NOT_A_SUBTITLE", ERROR)
        return plan
    if action == "convert":
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-i",
                    source["path"],
                    "-map",
                    "0:s:0",
                    "-c:s",
                    SUBTITLE_FORMATS[target],
                    output,
                ],
            )
        )
        if source["ext"] == "ass" and target != "ass":
            plan.note("ASS_STYLING_LOST", INFO)
        return plan
    if action not in ("shift", "clean"):
        raise errors.AppError(code="UNKNOWN_SUBTITLE_ACTION", raw=action)
    # Shift and clean run on parsed cues in Python, via SRT; FFmpeg converts back if needed.
    srt = output if target == "srt" else f"{work}/intermediate.srt"
    if source["ext"] not in ("srt", "vtt"):
        normalised = f"{work}/source.srt"
        plan.steps.append(
            Step(
                "ffmpeg",
                [*_ffmpeg(), "-i", source["path"], "-map", "0:s:0", "-c:s", "srt", normalised],
            )
        )
        text_source = normalised
    else:
        text_source = source["path"]
    offset = float(options.get("offset") or 0)
    plan.steps.append(
        Step(
            "python",
            action="CLEAN_CAPTIONS" if action == "clean" else "SHIFT",
            argv=[text_source, srt, str(offset)],
        )
    )
    if target != "srt":
        plan.steps.append(
            Step("ffmpeg", [*_ffmpeg(), "-i", srt, "-c:s", SUBTITLE_FORMATS[target], output])
        )
    return plan


def output_ext(op: str, source: dict[str, Any], options: dict[str, Any]) -> str:
    if op == "audio":
        return AUDIO_TARGETS.get(options.get("codec") or "mp3", ("", "mp3"))[1]
    if op == "trim":
        return trim_output_ext(source, options.get("mode") or "lossless")
    if op == "remux":
        return str(options.get("container") or "mkv")
    if op == "subtitle":
        return str(options.get("target") or "srt")
    raise errors.AppError(code="UNKNOWN_OPERATION", raw=op)


def separate_outputs(op: str, options: dict[str, Any]) -> int:
    """How many files an operation produces: several only for un-joined multi-segment cuts."""
    segments = options.get("segments") or []
    if op == "trim" and len(segments) > 1 and not options.get("join"):
        return len(segments)
    return 1


def build(
    op: str,
    source: dict[str, Any],
    options: dict[str, Any],
    output: str,
    work: str,
    extras: list[dict[str, Any]] | None = None,
    aac_encoder: str = "aac",
    keyframes: dict[float, float | None] | None = None,
) -> Plan:
    if op == "audio":
        return plan_audio(source, options, output, aac_encoder)
    if op == "trim":
        return plan_trim(source, options, output, work, keyframes)
    if op == "remux":
        return plan_remux(source, options, output, extras)
    if op == "subtitle":
        return plan_subtitle(source, options, output, work)
    raise errors.AppError(code="UNKNOWN_OPERATION", raw=op)
