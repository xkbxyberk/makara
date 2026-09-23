"""Download one job in its own process.

Protocol: one JSON request on stdin; JSON-lines events on stdout
    {"t": "stage", "stage": ...}
    {"t": "progress", "stage": ..., "progress": 0..1, "speed", "eta", "item_index", "item_count"}
    {"t": "done", "files": [...], "plan": {...}}
    {"t": "error", "code": ..., "raw": ...}
yt-dlp's own output goes to stderr through a logger; nothing else may write to stdout.

Pipeline:
1. side pass  -- subtitles, thumbnail, description, info.json (skip_download, once)
2. stream pass -- the raw streams, one file per selected format (yt-dlp resumes .part files,
   so a retried or restarted job continues where it stopped)
3. finalize   -- mux with our own FFmpeg command (languages, defaults, copy-vs-transcode
   decided by probing the real files), or rename for "separate", then move into place
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from app import errors
from app.doctor import listing_has
from app.ffmpeg import mux
from app.ffmpeg.probe import probe
from app.workers.inspect_worker import Collector
from app.ytdlp import naming, params

OUT: TextIO = sys.stdout
AUDIO_EXT = {"mp3": "mp3", "m4a": "m4a", "opus": "opus", "flac": "flac", "wav": "wav"}
SKIP_SUFFIXES = (".part", ".ytdl", ".temp", ".jpg", ".webp", ".png", ".vtt", ".srt")


def emit(event: dict[str, Any]) -> None:
    OUT.write(json.dumps(event) + "\n")
    OUT.flush()


class Progress:
    """Turns per-file yt-dlp hooks into one honest 0..1 for the whole download stage.

    Items are weighted by size, because the video is usually ~90% of the bytes: counting files
    equally would show 33% when the download is nearly finished.
    """

    def __init__(self, format_ids: list[str], expected: dict[str, int | None]) -> None:
        self.order = format_ids
        self.expected = expected
        self.done: dict[str, int] = {}
        self.total: dict[str, int] = {}
        self.last_emit = 0.0

    def _weights(self) -> dict[str, float]:
        known = [v for v in self.expected.values() if v]
        fallback = (sum(known) / len(known)) if known else 1.0
        return {
            fid: float(self.total.get(fid) or self.expected.get(fid) or fallback)
            for fid in self.order
        }

    def fraction(self) -> float:
        weights = self._weights()
        total = sum(weights.values()) or 1.0
        done = sum(min(float(self.done.get(fid, 0)), w) for fid, w in weights.items())
        return max(0.0, min(1.0, done / total))

    def hook(self, d: dict[str, Any]) -> None:
        filename = Path(str(d.get("filename") or ""))
        if not filename.name.startswith("stream."):
            return  # subtitle or thumbnail chatter from the side pass
        fid = str((d.get("info_dict") or {}).get("format_id") or "")
        if fid not in self.order:
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            self.total[fid] = int(total)
        self.done[fid] = int(d.get("downloaded_bytes") or 0)
        if d.get("status") == "finished":
            self.done[fid] = self.total.get(fid) or self.done[fid]
        now = time.monotonic()
        if d.get("status") == "finished" or now - self.last_emit >= 0.25:
            self.last_emit = now
            emit(
                {
                    "t": "progress",
                    "stage": "downloading",
                    "progress": round(self.fraction(), 4),
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                    "item_index": self.order.index(fid) + 1,
                    "item_count": len(self.order),
                }
            )


def _pp_hook(d: dict[str, Any]) -> None:
    if d.get("status") == "started" and d.get("postprocessor") not in ("MoveFiles", None):
        emit({"t": "stage", "stage": "postprocessing", "detail": d.get("postprocessor")})


def _aac_encoder() -> str:
    """AudioToolbox's AAC is better than FFmpeg's native one; use it when this build has it."""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    listing = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
    ).stdout
    return "aac_at" if listing_has(listing, "aac_at") else "aac"


def _find_side(work: Path, prefix: str) -> Path | None:
    """A finished side file (subtitle, thumbnail) -- never a half-written one."""
    for path in sorted(work.glob(f"{glob_escape(prefix)}.*")):
        if not path.name.endswith((".part", ".ytdl", ".temp")):
            return path
    return None


def glob_escape(text: str) -> str:
    return re.sub(r"([*?\[\]])", r"[\1]", text)


def _stream_file(work: Path, format_id: str) -> Path:
    for path in sorted(work.glob(f"stream.{glob_escape(format_id)}.*")):
        if not path.name.endswith(SKIP_SUFFIXES):
            return path
    raise errors.AppError(code="DOWNLOAD_INCOMPLETE", raw=f"no file for format {format_id}")


def _extract(url: str, log: Collector) -> dict[str, Any]:
    import yt_dlp

    with yt_dlp.YoutubeDL({**params.inspect_params(), "logger": log, "no_warnings": False}) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise errors.AppError(code=errors.classify(log.raw()), raw=log.raw())
        sanitized: dict[str, Any] = ydl.sanitize_info(info)
        return sanitized


def _base_params(work: Path, log: Collector) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    options = {
        **params.base_params(ffmpeg_location=ffmpeg),
        "logger": log,
        "no_warnings": False,
        "skip_download": False,
        "paths": {"home": str(work), "temp": str(work)},
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "overwrites": False,
    }
    return options


def _side_pass(req: dict[str, Any], info: dict[str, Any], work: Path, log: Collector) -> None:
    import yt_dlp

    extras = req.get("extras") or {}
    subs = req.get("subtitle_keys") or [] if req["mode"] != "audio" else []
    want_thumb = req["mode"] != "audio" and bool(
        extras.get("thumbnail") or extras.get("thumbnail_file")
    )
    if not (subs or want_thumb or extras.get("description") or extras.get("info_json")):
        return
    emit({"t": "stage", "stage": "preparing", "detail": "extras"})
    options = {
        **_base_params(work, log),
        "skip_download": True,
        "format": _selected(req)[0],
        "writesubtitles": bool(subs),
        "writeautomaticsub": bool(subs),
        # --sub-langs is a regex list; anchor and escape so "en" does not also match "en-GB".
        "subtitleslangs": [f"^{re.escape(k)}$" for k in subs],
        "subtitlesformat": "srt/vtt/best",
        "writethumbnail": want_thumb,
        "writedescription": bool(extras.get("description")),
        "writeinfojson": bool(extras.get("info_json")),
        "outtmpl": {
            "default": "side.%(ext)s",
            "subtitle": "sub",
            "thumbnail": "thumb",
            "description": "meta",
            "infojson": "meta",
        },
        "postprocessors": (
            [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}]
            if want_thumb
            else []
        ),
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.process_ie_result(copy.deepcopy(info), download=True)


def _selected(req: dict[str, Any]) -> list[str]:
    ids = [req.get("video_format_id"), *(req.get("audio_format_ids") or [])]
    return [str(i) for i in ids if i]


def _stream_pass(req: dict[str, Any], info: dict[str, Any], work: Path, log: Collector) -> None:
    import yt_dlp

    selected = _selected(req)
    progress = Progress(selected, {k: v for k, v in (req.get("expected_sizes") or {}).items()})
    options: dict[str, Any] = {
        **_base_params(work, log),
        # "," downloads each format as its own file; muxing is ours, not yt-dlp's merger.
        "format": ",".join(selected),
        "outtmpl": {"default": "stream.%(format_id)s.%(ext)s", "thumbnail": "thumb"},
        "progress_hooks": [progress.hook],
        "postprocessor_hooks": [_pp_hook],
    }
    if req["mode"] == "audio":
        codec = req.get("audio_codec") or "mp3"
        cover = bool((req.get("extras") or {}).get("thumbnail")) and codec != "wav"
        options["format"] = selected[0]
        options["writethumbnail"] = cover
        options["postprocessors"] = [
            *(
                [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}]
                if cover
                else []
            ),
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": str(req.get("audio_quality") or "0"),
                "nopostoverwrites": False,
            },
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True},
            *([{"key": "EmbedThumbnail", "already_have_thumbnail": False}] if cover else []),
        ]
    emit({"t": "stage", "stage": "downloading"})
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.process_ie_result(copy.deepcopy(info), download=True)


def _dest(stem: Path, suffix: str) -> Path:
    # Not with_suffix(): titles are full of dots ("v1.2 release") that it would eat.
    target = naming.unique(stem.parent / f"{stem.name}{suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _metadata(info: dict[str, Any]) -> dict[str, str]:
    date = str(info.get("upload_date") or "")
    return {
        "title": str(info.get("title") or ""),
        "artist": str(info.get("channel") or info.get("uploader") or ""),
        "date": date[:4] if len(date) >= 4 else "",
        "comment": str(info.get("webpage_url") or ""),
    }


def _finalize(
    req: dict[str, Any], info: dict[str, Any], work: Path
) -> tuple[list[str], dict[str, Any]]:
    mode = req["mode"]
    root = Path(req["download_dir"])
    extras = req.get("extras") or {}
    final_ext = {"mkv": "mkv", "compat_mp4": "mp4", "separate": "mkv"}.get(
        mode, AUDIO_EXT.get(req.get("audio_codec") or "mp3", "mp3")
    )
    stem = naming.resolve_inside(
        root, naming.render_relative(req["filename_template"], info, final_ext)
    )
    audio_langs = {t["format_id"]: t.get("language") for t in req.get("audio_tracks") or []}
    sub_langs = {t["key"]: t.get("language") for t in req.get("subtitle_tracks") or []}
    files: list[Path] = []
    plan: dict[str, Any] = {}

    subtitle_files: list[tuple[str, Path]] = []
    for key in req.get("subtitle_keys") or []:
        found = _find_side(work, f"sub.{key}")
        if found is not None:
            subtitle_files.append((key, found))
    thumb = next(iter(sorted(work.glob("thumb*.jpg"))), None)

    if mode in ("mkv", "compat_mp4"):
        container = "mkv" if mode == "mkv" else "mp4"
        inputs: list[mux.MuxInput] = []
        video_id = req.get("video_format_id")
        if video_id:
            path = _stream_file(work, video_id)
            inputs.append(mux.MuxInput(path, "video", None, probe(path).get("streams", [])))
        for fid in req.get("audio_format_ids") or []:
            path = _stream_file(work, fid)
            inputs.append(
                mux.MuxInput(path, "audio", audio_langs.get(fid), probe(path).get("streams", []))
            )
        for key, path in subtitle_files:
            inputs.append(
                mux.MuxInput(
                    path, "subtitle", sub_langs.get(key) or key, probe(path).get("streams", [])
                )
            )
        chapters_file = None
        if info.get("chapters"):
            chapters_file = work / "chapters.ffmeta"
            chapters_file.write_text(mux.ffmetadata_chapters(info["chapters"]), encoding="utf-8")
        output = work / f"output.{container}"
        argv, plan = mux.build_mux_argv(
            container=container,
            inputs=inputs,
            output=output,
            thumbnail=thumb if extras.get("thumbnail") else None,
            chapters_file=chapters_file,
            metadata=_metadata(info),
            aac_encoder=_aac_encoder(),
            separate_audio=bool(req.get("audio_format_ids")),
        )
        transcoding = any(step.startswith("transcode") for steps in plan.values() for step in steps)
        stage = "converting" if transcoding else "merging"
        emit({"t": "stage", "stage": stage})
        duration = float(info.get("duration") or 0) or None
        last = [0.0]

        def report(fraction: float) -> None:
            now = time.monotonic()
            if fraction >= 1.0 or now - last[0] >= 0.25:
                last[0] = now
                emit({"t": "progress", "stage": stage, "progress": round(fraction, 4)})

        mux.run_with_progress(argv, duration, report)
        target = _dest(stem, f".{container}")
        shutil.move(output, target)
        files.append(target)
    elif mode == "separate":
        seen: set[str] = set()
        video_id = req.get("video_format_id")
        if video_id:
            path = _stream_file(work, video_id)
            target = _dest(stem, path.suffix)
            shutil.move(path, target)
            files.append(target)
        for fid in req.get("audio_format_ids") or []:
            path = _stream_file(work, fid)
            label = audio_langs.get(fid) or fid
            label = f"{label}.{fid}" if label in seen else label
            seen.add(label)
            target = _dest(stem, f".{label}{path.suffix}")
            shutil.move(path, target)
            files.append(target)
        for key, path in subtitle_files:
            # "<video>.<lang>.srt" next to "<video>.<ext>" is what IINA and VLC auto-load.
            # SRT is the sidecar every player reads; ASS is kept as-is so styling survives.
            if path.suffix == ".vtt":
                converted = path.with_suffix(".srt")
                mux.run_with_progress(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(path),
                        "-c:s",
                        "srt",
                        "-progress",
                        "pipe:1",
                        str(converted),
                    ],
                    None,
                    lambda _fraction: None,
                )
                path = converted
            target = _dest(stem, f".{key}{path.suffix}")
            shutil.move(path, target)
            files.append(target)
    else:  # audio
        fid = _selected(req)[0]
        path = _stream_file(work, fid)
        target = _dest(stem, path.suffix)
        shutil.move(path, target)
        files.append(target)

    if extras.get("thumbnail_file") and thumb is not None and thumb.exists():
        target = _dest(stem, ".jpg")
        shutil.copy2(thumb, target)
        files.append(target)
    for name, suffix, wanted in (
        ("meta.description", ".description.txt", extras.get("description")),
        ("meta.info.json", ".info.json", extras.get("info_json")),
    ):
        source = work / name
        if wanted and source.exists():
            target = _dest(stem, suffix)
            shutil.move(source, target)
            files.append(target)
    return [str(f) for f in files], plan


def _cleanup(req: dict[str, Any], work: Path) -> None:
    """Remove the job's scratch directory -- only ever our own, never anything else."""
    scratch_root = (Path(req["download_dir"]) / ".vd-work").resolve()
    if work.resolve().parent == scratch_root and work.name == req["job_id"]:
        shutil.rmtree(work, ignore_errors=True)


def run(req: dict[str, Any]) -> int:
    log = Collector()
    work = Path(req["work_dir"])
    try:
        work.mkdir(parents=True, exist_ok=True)
        emit({"t": "stage", "stage": "preparing"})
        info = req.get("info") or _extract(req["url"], log)
        _side_pass(req, info, work, log)
        _stream_pass(req, info, work, log)
        files, plan = _finalize(req, info, work)
    except errors.AppError as exc:
        emit({"t": "error", "code": exc.code, "raw": exc.raw or log.raw()})
        return 1
    except RuntimeError as exc:  # FFmpeg exited non-zero
        emit({"t": "error", "code": "FFMPEG_FAILED", "raw": str(exc)})
        return 1
    except OSError as exc:
        code = "DISK_FULL" if exc.errno == 28 else errors.classify(str(exc))
        emit({"t": "error", "code": code, "raw": log.raw(exc)})
        return 1
    except Exception as exc:  # anything yt-dlp raises
        emit({"t": "error", "code": errors.classify(str(exc)), "raw": log.raw(exc)})
        return 1
    _cleanup(req, work)
    emit({"t": "done", "files": files, "plan": plan})
    return 0


def main() -> int:
    global OUT
    request = json.loads(sys.stdin.read())
    OUT = os.fdopen(os.dup(1), "w")
    sys.stdout = sys.stderr  # yt-dlp or a library printing must not corrupt the event stream
    return run(request)


if __name__ == "__main__":
    raise SystemExit(main())
