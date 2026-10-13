"""Studio operations as data: each becomes a list of steps (FFmpeg argv or a Python action).

The same plan is shown to Berk before a run ("the exact FFmpeg command") and executed by the
studio worker, so what is previewed is what runs. Pure functions; nothing here touches disk
except `probe_source` / `keyframes_near`, which only read.
"""

from __future__ import annotations

import contextlib
import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import errors
from app.ffmpeg import binaries
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
        binaries.ffmpeg(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
    ]


def _progress(output: str) -> list[str]:
    return ["-progress", "pipe:1", "-nostats", output]


# ---- reading the source ------------------------------------------------------------------
SUBTITLE_EXTS = (".srt", ".vtt", ".ass", ".ssa", ".sub")


def probe_source(path: Path) -> dict[str, Any]:
    """Streams, duration and chapters of a user-chosen file. Refuses anything not media."""
    if not path.is_absolute() or not path.is_file():
        raise errors.AppError(code="SOURCE_NOT_FOUND", raw=str(path))
    charset = "UTF-8"
    if path.suffix.lower() in SUBTITLE_EXTS and path.stat().st_size < 20_000_000:
        charset = read_subtitle_text(path)[1]
    argv = [binaries.ffprobe(), "-v", "error"]
    if charset != "UTF-8":
        argv += ["-sub_charenc", charset]  # FFmpeg rejects non-UTF-8 text subtitles otherwise
    argv += ["-print_format", "json", "-show_streams", "-show_format", "-show_chapters", str(path)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    data = json.loads(proc.stdout or "{}") if proc.returncode == 0 else {}
    streams = data.get("streams") or []
    if not streams:
        raise errors.AppError(code="SOURCE_NOT_MEDIA", raw=proc.stderr[-2000:])
    duration = data.get("format", {}).get("duration")
    video = next(
        (
            st
            for st in streams
            if st.get("codec_type") == "video"
            and not (st.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    youtube_auto = False
    if path.suffix.lower() == ".vtt" and path.stat().st_size < 5_000_000:
        from app.studio.subtitles import looks_like_youtube_auto_captions

        youtube_auto = looks_like_youtube_auto_captions(read_subtitle_text(path)[0])
    return {
        "charset": charset,
        "youtube_auto_captions": youtube_auto,
        "path": str(path),
        "name": path.name,
        "ext": path.suffix.lstrip(".").lower(),
        "size": path.stat().st_size,
        "duration": float(duration) if duration else None,
        "streams": [
            {
                "index": st.get("index"),
                "type": st.get("codec_type"),
                "codec": st.get("codec_name"),
                "language": (st.get("tags") or {}).get("language"),
                "title": (st.get("tags") or {}).get("title"),
                "default": bool((st.get("disposition") or {}).get("default")),
                "attached_pic": bool((st.get("disposition") or {}).get("attached_pic")),
                "width": st.get("width"),
                "height": st.get("height"),
                "channels": st.get("channels"),
                "sample_rate": st.get("sample_rate"),
                "frame_rate": st.get("r_frame_rate") if st.get("codec_type") == "video" else None,
            }
            for st in streams
        ],
        # The video's frame grid (Stüdyo snaps cuts to it). None with a variable frame rate:
        # "frame N" of a nominal rate is then no real frame, and cuts go by time (measured: a
        # joined cut by such frames lost a third of its picture against its sound).
        "frame_rate": (
            _rate(video.get("r_frame_rate")) if video is not None and not _variable(video) else None
        ),
        "variable_frame_rate": video is not None and _variable(video),
        # Where frame 0 is: the first video frame, in seconds from the start of the file (an
        # MKV's picture can start after its sound; an MPEG-TS starts nowhere near 0).
        "video_start": _video_start(video, data.get("format") or {}),
        "chapters": [
            {
                "start": float(c["start_time"]),
                "end": float(c["end_time"]),
                "title": (c.get("tags") or {}).get("title"),
            }
            for c in data.get("chapters") or []
        ],
    }


def _video_start(video: dict[str, Any] | None, fmt: dict[str, Any]) -> float:
    if video is None:
        return 0.0
    try:
        offset = float(video.get("start_time") or 0) - float(fmt.get("start_time") or 0)
    except ValueError:
        return 0.0
    return round(max(0.0, offset), 6)


def _rate(text: Any) -> dict[str, int] | None:
    """ "30000/1001" -> {"num": 30000, "den": 1001}; nothing for "0/0" or junk."""
    try:
        num, den = (int(part) for part in str(text).split("/", 1))
    except (TypeError, ValueError):
        return None
    if num <= 0 or den <= 0 or num / den > 1000:
        return None
    return {"num": num, "den": den}


def _variable(stream: dict[str, Any]) -> bool:
    nominal, average = _rate(stream.get("r_frame_rate")), _rate(stream.get("avg_frame_rate"))
    if nominal is None or average is None:
        return False
    a, b = nominal["num"] / nominal["den"], average["num"] / average["den"]
    return abs(a - b) / a > 0.01


def keyframes(path: Path, limit: int = 50_000) -> list[float]:
    """Every video keyframe's time (seconds from the first frame): where a lossless cut can
    start. Only keyframes are read (`-skip_frame nokey`), so even a long file takes seconds."""
    data = _ffprobe_json(
        [
            binaries.ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "V:0",
            "-skip_frame",
            "nokey",
            "-show_entries",
            "frame=pts_time:stream=start_time",
            "-of",
            "json",
            str(path),
        ],
        timeout=180,
    )
    # Seconds from the video's own first frame: the origin Stüdyo's frame numbers count from.
    try:
        origin = float((data.get("streams") or [{}])[0].get("start_time") or 0)
    except ValueError:
        origin = 0.0
    times: list[float] = []
    for frame in data.get("frames") or []:
        with contextlib.suppress(KeyError, ValueError):
            times.append(round(max(0.0, float(frame["pts_time"]) - origin), 6))
    return sorted(set(times))[:limit]


def _ffprobe_json(argv: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        out = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        ).stdout
        data: dict[str, Any] = json.loads(out or "{}")
        return data
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def keyframe_at_or_before(path: Path, seconds: float) -> float | None:
    """Where a stream-copy cut requested at `seconds` will really start: the last video
    keyframe at or before it (seconds from the start of the file).

    `V` (capital) skips attached pictures, so an audio file's cover is not mistaken for video;
    without real video a stream copy cuts at packet granularity and nothing moves. Times are
    made relative to the container's start_time (MPEG-TS files rarely start at 0), and the
    search window widens for long groups of pictures.
    """
    if seconds <= 0:
        return 0.0
    ffprobe = binaries.ffprobe()
    info = _ffprobe_json(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "V:0",
            "-show_entries",
            "stream=index:format=start_time",
            "-of",
            "json",
            str(path),
        ]
    )
    if not info.get("streams"):
        return seconds
    try:
        origin = float(info.get("format", {}).get("start_time") or 0)
    except ValueError:
        origin = 0.0
    for window in (20.0, 120.0, 900.0):
        lo = max(origin, origin + seconds - window)
        data = _ffprobe_json(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "V:0",
                "-skip_frame",
                "nokey",
                "-show_entries",
                "frame=pts_time",
                "-of",
                "json",
                "-read_intervals",
                f"{lo:.3f}%{origin + seconds + 0.05:.3f}",
                str(path),
            ]
        )
        times = []
        for frame in data.get("frames") or []:
            try:
                times.append(float(frame["pts_time"]) - origin)
            except (KeyError, ValueError):
                continue
        before = [t for t in times if t <= seconds + 1e-3]
        if before:
            return max(0.0, max(before))
        if lo <= origin:
            break
    return 0.0


def read_subtitle_text(path: Path) -> tuple[str, str]:
    """-> (text, FFmpeg charset name). Old Turkish SRT files are Windows-1254, not UTF-8;
    decoding them as UTF-8 would silently turn "Şişli" into "�i�li"."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        return raw.decode("cp1254", errors="replace"), "CP1254"


# ---- option parsing -----------------------------------------------------------------------
def _number(options: dict[str, Any], key: str, default: float | None = None) -> float | None:
    """Options arrive from the UI as JSON; a malformed value is a coded error, never a 500."""
    value = options.get(key)
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise errors.AppError(code="INVALID_OPTION", raw=f"{key}={value!r}") from None
    if not math.isfinite(number):
        raise errors.AppError(code="INVALID_OPTION", raw=f"{key}={value!r}")
    return number


def _video_streams(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in source["streams"] if s["type"] == "video" and not s["attached_pic"]]


# ---- audio: convert / extract / loudness -----------------------------------------------------
OPUS_RATES = {48000, 24000, 16000, 12000, 8000}


def audio_encoder_args(codec: str, bitrate: float | None, aac_encoder: str = "aac") -> list[str]:
    encoder = aac_encoder if codec == "m4a" else AUDIO_TARGETS[codec][0]
    args = ["-c:a", encoder]
    if codec in LOSSY_AUDIO and bitrate:
        args += ["-b:a", f"{int(bitrate)}k"]
    return args


def loudnorm_filter(measured: dict[str, Any] | None = None) -> str:
    target = LOUDNESS_TARGET
    base = f"loudnorm=I={target['I']}:TP={target['TP']}:LRA={target['LRA']}"
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
        raise errors.AppError(code="UNKNOWN_AUDIO_CODEC", raw=str(codec))
    audio = [s for s in source["streams"] if s["type"] == "audio"]
    plan = Plan(steps=[], ext=AUDIO_TARGETS[codec][1])
    if not audio:
        plan.note("NO_AUDIO_IN_SOURCE", ERROR)
        return plan
    pick = int(_number(options, "audio_index", 0) or 0)
    if not 0 <= pick < len(audio):
        pick = 0
    duration = source.get("duration")
    covers = [s for s in source["streams"] if s["attached_pic"]]
    keep_cover = bool(covers) and codec in ("mp3", "m4a", "flac")
    maps = ["-map", f"0:a:{pick}"]
    extra: list[str] = []
    if keep_cover:
        maps += ["-map", f"0:{covers[0]['index']}"]
        extra += ["-c:v", "copy", "-disposition:v:0", "attached_pic"]
    sample_rate = _number(options, "sample_rate")
    if codec == "opus" and sample_rate and int(sample_rate) not in OPUS_RATES:
        plan.note("OPUS_48K", INFO, requested=int(sample_rate))
        sample_rate = 48000  # libopus only encodes 48/24/16/12/8 kHz
    if not sample_rate and options.get("loudnorm"):
        # loudnorm resamples to 192 kHz internally; pin a normal rate for the output.
        sample_rate = 48000 if codec == "opus" else 44100
    rate = ["-ar", str(int(sample_rate))] if sample_rate else []
    channels_n = _number(options, "channels")
    channels = ["-ac", str(int(channels_n))] if channels_n else []
    encode = audio_encoder_args(codec, _number(options, "bitrate"), aac_encoder)
    tail = [*encode, *rate, *channels, *extra, "-map_metadata", "0", *_progress(output)]
    if options.get("loudnorm"):
        # Two passes: measure, then correct linearly -- the accurate way to hit -16 LUFS.
        measure = [
            binaries.ffmpeg(),
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
        ]
        plan.steps.append(Step("ffmpeg", measure, action="LOUDNESS_MEASURE", duration=duration))
        plan.steps.append(
            Step(
                "ffmpeg",
                [*_ffmpeg(), "-i", source["path"], *maps, "-af", "{LOUDNORM_MEASURED}", *tail],
                action="LOUDNESS_APPLY",
                duration=duration,
            )
        )
        plan.note("LOUDNESS_TWO_PASS", INFO, target=LOUDNESS_TARGET["I"])
    else:
        plan.steps.append(
            Step("ffmpeg", [*_ffmpeg(), "-i", source["path"], *maps, *tail], duration=duration)
        )
    source_codec = audio[pick]["codec"]
    if codec in ("flac", "wav") and source_codec not in ("flac", "alac", "pcm_s16le", "pcm_s24le"):
        plan.note("LOSSLESS_FROM_LOSSY", INFO, codec=source_codec)
    return plan


# ---- trim / cut / join --------------------------------------------------------------------
def segment_frames(source: dict[str, Any], seg: dict[str, Any]) -> tuple[int, int] | None:
    """A segment given as frames ([start_frame, end_frame): the first frame kept and the first
    frame dropped), as the native Stüdyo sends it; None for one given in seconds."""
    rate = source.get("frame_rate")
    first, stop = seg.get("start_frame"), seg.get("end_frame")
    if rate is None or not isinstance(first, int) or not isinstance(stop, int):
        return None
    return first, stop


def segment_times(source: dict[str, Any], seg: dict[str, Any]) -> tuple[float, float]:
    """Seconds from the start of the file. Frames go through the source's own frame rate (never
    one the client claims), counted from the video's first frame: frame k starts at
    video_start + k * den / num."""
    frames = segment_frames(source, seg)
    if frames is not None:
        rate = source["frame_rate"]
        origin = source.get("video_start") or 0.0
        step = rate["den"] / rate["num"]
        return origin + frames[0] * step, origin + frames[1] * step
    return _number(seg, "start", 0.0) or 0.0, _number(seg, "end", 0.0) or 0.0


def _validate_segments(
    source: dict[str, Any], segments: list[dict[str, Any]], plan: Plan
) -> list[tuple[float, float]]:
    duration = source.get("duration") or 0
    clean: list[tuple[float, float]] = []
    for seg in segments:
        start, end = segment_times(source, seg)
        frames = segment_frames(source, seg)
        if (frames is not None and (frames[0] < 0 or frames[1] <= frames[0])) or (
            start < 0 or end <= start or (duration and start >= duration)
        ):
            plan.note("INVALID_SEGMENT", ERROR, start=round(start, 3), end=round(end, 3))
            continue
        clean.append((start, min(end, duration) if duration else end))
    if not clean and not any(n["code"] == "INVALID_SEGMENT" for n in plan.notices):
        plan.note("NO_SEGMENTS", ERROR)
    return clean


# How far before an accurate cut the input seek lands (the exact seek decodes the rest).
COARSE_SEEK_MARGIN = 10.0

# Frame-accurate cuts of audio-only files keep the family of the source.
AUDIO_ONLY_ACCURATE = {
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-q:a", "2"]),
    "flac": ("flac", ["-c:a", "flac"]),
    "wav": ("wav", ["-c:a", "pcm_s16le"]),
    "opus": ("opus", ["-c:a", "libopus", "-b:a", "160k"]),
    "ogg": ("ogg", ["-c:a", "libopus", "-b:a", "160k"]),
}


def trim_output_ext(source: dict[str, Any], mode: str) -> str:
    ext = source["ext"]
    if mode == "lossless":
        return ext
    if not _video_streams(source):
        return AUDIO_ONLY_ACCURATE.get(ext, ("m4a", []))[0]
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
    raw_segments = options.get("segments") or []
    segments = _validate_segments(source, raw_segments, plan)
    if not segments:
        return plan
    # Segments chosen frame by frame (the native Stüdyo): cut on exactly those frames. Only
    # when every segment is valid -- an invalid one blocks the plan anyway.
    exact: list[tuple[int, int] | None] = (
        [segment_frames(source, seg) for seg in raw_segments]
        if len(segments) == len(raw_segments)
        else [None] * len(segments)
    )
    rate = source.get("frame_rate")
    half = 0.5 * rate["den"] / rate["num"] if rate else 0.0
    if len(segments) > 1 and not join:
        plan.note("SEGMENTS_SEPARATE", INFO, count=len(segments))
    has_video = bool(_video_streams(source))
    has_audio = any(s["type"] == "audio" for s in source["streams"])
    has_cover = any(s["attached_pic"] for s in source["streams"])
    joined = join and len(segments) > 1

    def target(n: int) -> str:
        if joined:
            return f"{work}/segment_{n}.{ext}"
        return output if len(segments) == 1 else output.replace("{N}", str(n + 1))

    if mode == "lossless":
        plan.note("LOSSLESS_KEYFRAMES", INFO)
        for start, _ in segments:
            actual = (keyframes or {}).get(start)
            if actual is not None and start - actual > 0.05:
                plan.note("CUT_MOVES_TO_KEYFRAME", WARN, requested=start, actual=round(actual, 3))
        # A joined cut must not carry cover art: the concat demuxer loses the attached-picture
        # flag and the cover turns into a video track (or fails outright in M4A).
        maps = ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?"] if joined else ["-map", "0"]
        if joined and has_cover:
            plan.note("JOIN_DROPS_COVER", INFO)
        pieces = []
        for n, (start, end) in enumerate(segments):
            pieces.append(target(n))
            # A stream copy starts on the keyframe at or before -ss: half a frame past the
            # chosen frame keeps rounding from ever landing on the keyframe before it.
            seek = f"{start + half:.6f}" if exact[n] else f"{start:.3f}"
            plan.steps.append(
                Step(
                    "ffmpeg",
                    [
                        *_ffmpeg(),
                        "-ss",
                        seek,
                        "-to",
                        f"{end:.6f}" if exact[n] else f"{end:.3f}",
                        "-i",
                        source["path"],
                        *maps,
                        "-c",
                        "copy",
                        "-avoid_negative_ts",
                        "make_zero",
                        *_progress(target(n)),
                    ],
                    duration=end - start,
                )
            )
        if joined:
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
    video_enc = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if has_video:
        plan.note("ACCURATE_REENCODES", INFO)
        audio_enc = ["-c:a", "aac", "-b:a", "192k"]
    else:
        plan.note("ACCURATE_AUDIO_REENCODES", INFO)
        audio_enc = AUDIO_ONLY_ACCURATE.get(
            source["ext"], ("m4a", ["-c:a", "aac", "-b:a", "192k"])
        )[1]
    if joined:
        plan.note("JOIN_FIRST_TRACKS_ONLY", INFO)
        parts, labels = [], []
        for n, (start, end) in enumerate(segments):
            frames = exact[n]
            if has_video:
                cut = (
                    f"trim=start_frame={frames[0]}:end_frame={frames[1]}"
                    if frames
                    else f"trim=start={start:.3f}:end={end:.3f}"
                )
                parts.append(f"[0:V:0]{cut},setpts=PTS-STARTPTS[v{n}]")
                labels.append(f"[v{n}]")
            if has_audio:
                span = (
                    f"start={start:.6f}:end={end:.6f}"
                    if frames
                    else f"start={start:.3f}:end={end:.3f}"
                )
                parts.append(f"[0:a:0]atrim={span},asetpts=PTS-STARTPTS[a{n}]")
                labels.append(f"[a{n}]")
        concat = f"{''.join(labels)}concat=n={len(segments)}:v={int(has_video)}:a={int(has_audio)}"
        outs = (["[v]"] if has_video else []) + (["[a]"] if has_audio else [])
        graph = ";".join([*parts, concat + "".join(outs)])
        maps_out = [x for label in outs for x in ("-map", label)]
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    "-i",
                    source["path"],
                    "-filter_complex",
                    graph,
                    *maps_out,
                    *(video_enc if has_video else []),
                    *(audio_enc if has_audio else []),
                    *_progress(output),
                ],
                duration=sum(e - s for s, e in segments),
            )
        )
        return plan
    for n, (start, end) in enumerate(segments):
        subs = ["-map", "0:s?", "-c:s", "mov_text" if ext == "mp4" else "copy"] if has_video else []
        frames = exact[n]
        # Frame by frame: seek a hair (1 ms, at most a quarter frame) before the first frame
        # kept -- an accurate seek keeps the first frame at or after it, so rounding can never
        # drop it -- then exactly that many frames. Half a frame was measured to shift the
        # output's first frame by a whole frame and lose the last one, and to put the sound
        # 20 ms ahead of the picture; a millisecond rounds away.
        lead = min(0.001, half / 2) if rate else 0.0
        # Two seeks: a coarse one on the input, well before the cut (fast; an MPEG-TS lands
        # only roughly where asked, and so not after the cut), then an exact one on the decoded
        # frames, by their timestamps -- which the coarse seek keeps relative to where it asked.
        coarse = max(0.0, math.floor((start - COARSE_SEEK_MARGIN) * 1000) / 1000)
        fine = max(0.0, start - lead - coarse)
        count = ["-frames:v", str(frames[1] - frames[0])] if frames and has_video else []
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    *(["-ss", f"{coarse:.3f}"] if coarse > 0 else []),
                    "-i",
                    source["path"],
                    "-ss",
                    f"{fine:.6f}" if frames else f"{fine:.3f}",
                    "-t",
                    f"{end - start:.6f}" if frames else f"{end - start:.3f}",
                    *count,
                    *(["-map", "0:V:0"] if has_video else []),
                    "-map",
                    "0:a?",
                    *subs,
                    *(video_enc if has_video else []),
                    *audio_enc,
                    *_progress(target(n)),
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
    """Change container and edit tracks without re-encoding (subtitles may be converted).

    The output order follows the track list. Every kept track gets an explicit language
    ("und" when cleared) and title, so clearing a field really clears it.
    """
    container = options.get("container") or "mkv"
    if container not in ("mkv", "mp4", "mov"):
        raise errors.AppError(code="UNKNOWN_CONTAINER", raw=str(container))
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
        if s["type"] in ("video", "audio", "subtitle")
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
        index = int(_number(track, "input", 0) or 0)
        stream = None
        if 0 <= index < len(inputs):
            stream = next(
                (s for s in inputs[index]["streams"] if s["index"] == track.get("stream")), None
            )
        if stream is None or stream["type"] not in counts:
            plan.note("UNKNOWN_TRACK", ERROR)
            continue
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
        language = str(track.get("language") or "").strip()
        per_stream += [
            f"-metadata:s:{spec}",
            f"language={iso639_2(language) if language else 'und'}",
        ]
        per_stream += [f"-metadata:s:{spec}", f"title={track.get('title') or ''}"]
        if stream["attached_pic"]:
            per_stream += [f"-disposition:{spec}", "attached_pic"]
        else:
            per_stream += [f"-disposition:{spec}", "default" if track.get("default") else "0"]
        counts[kind] += 1
        kept += 1
    if kept == 0:
        plan.note("NO_TRACKS_KEPT", ERROR)
    # MKV fonts (and other attachments) travel along; ASS subtitles need them to render.
    attachments = ["-map", "0:t?", "-c:t", "copy"] if container == "mkv" else []
    tail = ["-movflags", "+faststart"] if container in ("mp4", "mov") else []
    plan.steps.append(
        Step(
            "ffmpeg",
            [
                *argv,
                *maps,
                *attachments,
                *per_stream,
                "-map_chapters",
                "0",
                *tail,
                *_progress(output),
            ],
            duration=source.get("duration"),
        )
    )
    plan.note("REMUX_NO_REENCODE", INFO)
    return plan


# ---- subtitle files ----------------------------------------------------------------------------
def _subtitle_input(source: dict[str, Any]) -> list[str]:
    charset = source.get("charset") or "UTF-8"
    return (["-sub_charenc", charset] if charset != "UTF-8" else []) + ["-i", source["path"]]


def plan_subtitle(source: dict[str, Any], options: dict[str, Any], output: str, work: str) -> Plan:
    action = options.get("action") or "convert"
    target = options.get("target") or "srt"
    if target not in SUBTITLE_FORMATS:
        raise errors.AppError(code="UNKNOWN_SUBTITLE_FORMAT", raw=str(target))
    plan = Plan(steps=[], ext=target)
    if not any(s["type"] == "subtitle" for s in source["streams"]):
        plan.note("NOT_A_SUBTITLE", ERROR)
        return plan
    if source.get("charset", "UTF-8") != "UTF-8":
        plan.note("LEGACY_ENCODING", INFO, charset=source["charset"])
    if action == "convert":
        plan.steps.append(
            Step(
                "ffmpeg",
                [
                    *_ffmpeg(),
                    *_subtitle_input(source),
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
        raise errors.AppError(code="UNKNOWN_SUBTITLE_ACTION", raw=str(action))
    offset = _number(options, "offset", 0.0) or 0.0
    if source["ext"] in ("ass", "ssa"):
        plan.note("ASS_STYLING_LOST", INFO)
    # Shift and clean run on parsed cues in Python, via SRT; FFmpeg converts back if needed.
    srt = output if target == "srt" else f"{work}/intermediate.srt"
    if source["ext"] not in ("srt", "vtt"):
        normalised = f"{work}/source.srt"
        plan.steps.append(
            Step(
                "ffmpeg",
                [*_ffmpeg(), *_subtitle_input(source), "-map", "0:s:0", "-c:s", "srt", normalised],
            )
        )
        text_source = normalised
    else:
        text_source = source["path"]
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
