"""Run one Studio operation in its own process. Same protocol as the download worker.

Every output is produced inside the job's scratch directory first; only when all steps have
succeeded are final names claimed (atomically, never over an existing file) and the results
moved next to the source. The source file itself is only ever read.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, TextIO

from app import errors
from app.ffmpeg import mux
from app.studio import ops, subtitles
from app.workers.download_worker import _aac_encoder, _describe
from app.ytdlp import naming

OUT: TextIO = sys.stdout


def emit(event: dict[str, Any]) -> None:
    OUT.write(json.dumps(event) + "\n")
    OUT.flush()


def _concat_line(path: str) -> str:
    # The concat demuxer's quoting: wrap in single quotes, escape embedded ones as '\''.
    return "file '" + path.replace("'", "'\\''") + "'\n"


def _run_python(step: ops.Step) -> None:
    if step.action == "WRITE_CONCAT_LIST":
        listing, *pieces = step.argv
        Path(listing).write_text("".join(_concat_line(p) for p in pieces), encoding="utf-8")
        return
    if step.action in ("SHIFT", "CLEAN_CAPTIONS"):
        source, target, offset = step.argv
        text = Path(source).read_text(encoding="utf-8-sig", errors="replace")
        cues = subtitles.parse(text)
        if step.action == "SHIFT":
            cues = subtitles.shift(cues, float(offset))
        else:
            cues = subtitles.clean_auto_captions(cues)
        if not cues:
            raise errors.AppError(code="SUBTITLE_EMPTY", raw=source)
        Path(target).write_text(subtitles.to_srt(cues), encoding="utf-8")
        return
    raise errors.AppError(code="UNKNOWN_OPERATION", raw=step.action)


def _loudnorm_measurement(stderr: str) -> dict[str, Any]:
    blocks = re.findall(r"\{[^{}]*\}", stderr)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if "input_i" in data:
            return data
    raise errors.AppError(code="LOUDNESS_MEASURE_FAILED", raw=stderr[-2000:])


def _execute(plan: ops.Plan) -> None:
    weights = [(s.duration or 1.0) * s.weight for s in plan.steps]
    total = sum(weights) or 1.0
    done = 0.0
    measured: dict[str, Any] | None = None
    last = [0.0]
    emit({"t": "stage", "stage": "processing"})
    for step, weight in zip(plan.steps, weights, strict=True):
        if step.kind == "python":
            _run_python(step)
            continue
        argv = [
            ops.loudnorm_filter(measured) if a == "{LOUDNORM_MEASURED}" and measured else a
            for a in step.argv
        ]
        base = done

        def report(fraction: float, base: float = base, weight: float = weight) -> None:
            now = time.monotonic()
            if fraction >= 1.0 or now - last[0] >= 0.25:
                last[0] = now
                overall = (base + fraction * weight) / total
                emit({"t": "progress", "stage": "processing", "progress": round(overall, 4)})

        stderr = mux.run_with_progress(argv, step.duration, report)
        if step.action == "LOUDNESS_MEASURE":
            measured = _loudnorm_measurement(stderr)
        done += weight


def run(req: dict[str, Any]) -> int:
    work = Path(req["work_dir"])
    placeholders: list[Path] = []
    try:
        work.mkdir(parents=True, exist_ok=True)
        emit({"t": "stage", "stage": "preparing"})
        # Re-read the source now: it may have changed since the plan was shown.
        source = ops.probe_source(Path(req["source_path"]))
        extras = [ops.probe_source(Path(p)) for p in req.get("extra_paths") or []]
        op, options = req["op"], req.get("options") or {}
        ext = ops.output_ext(op, source, options)
        count = ops.separate_outputs(op, options)
        output = str(work / (f"output_{{N}}.{ext}" if count > 1 else f"output.{ext}"))
        plan = ops.build(op, source, options, output, str(work), extras, _aac_encoder())
        if plan.blocking:
            codes = ", ".join(n["code"] for n in plan.notices if n["level"] == "error")
            raise errors.AppError(code="SELECTION_INVALID", raw=codes)
        _execute(plan)
        emit({"t": "stage", "stage": "finalizing"})
        produced = [Path(output.replace("{N}", str(n + 1))) for n in range(count)]
        suffixes = [f".{n + 1}.{ext}" for n in range(count)] if count > 1 else [f".{ext}"]
        placeholders = naming.claim(
            Path(req["output_dir"]),
            PurePosixPath(naming.safe_component(req["output_name"])),
            suffixes,
        )
        for source_file, target in zip(produced, placeholders, strict=True):
            os.replace(source_file, target)
        files = [str(p) for p in placeholders]
    except errors.AppError as exc:
        naming.release(placeholders)
        emit({"t": "error", "code": exc.code, "raw": exc.raw})
        return 1
    except RuntimeError as exc:
        naming.release(placeholders)
        emit({"t": "error", "code": "FFMPEG_FAILED", "raw": str(exc)})
        return 1
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        naming.release(placeholders)
        code = "DISK_FULL" if isinstance(exc, OSError) and exc.errno == 28 else errors.UNKNOWN
        emit({"t": "error", "code": code, "raw": repr(exc)})
        return 1
    shutil.rmtree(work, ignore_errors=True)
    media = [f for f in files if Path(f).suffix.lstrip(".") not in ops.SUBTITLE_FORMATS]
    outputs = _describe(media, req["job_id"]) if media else []
    meta = {"title": Path(files[0]).stem, "extractor_key": "Studio", "channel": None}
    emit(
        {"t": "done", "files": files, "plan": {}, "outputs": outputs, "meta": meta, "warnings": []}
    )
    return 0


def main() -> int:
    global OUT
    request = json.loads(sys.stdin.read())
    OUT = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return run(request)


if __name__ == "__main__":
    raise SystemExit(main())
