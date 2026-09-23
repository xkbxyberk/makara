"""Studio operations through the real worker and real FFmpeg; every result checked by ffprobe."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.ffmpeg.probe import probe
from app.studio import ops
from app.workers import studio_worker
from tests.test_subtitles import YOUTUBE_ASR

# video_h264.mp4 is 4 s at 25 fps with a keyframe every 25 frames: keyframes at 0, 1, 2, 3 s.


@pytest.fixture
def workspace(tmp_path: Path, test_media: Path) -> Path:
    for name in ("video_h264.mp4", "audio_en.m4a", "audio_tr.m4a", "sub_en.vtt"):
        shutil.copy2(test_media / name, tmp_path / name)
    return tmp_path


def run_op(
    workspace: Path,
    source: Path,
    op: str,
    options: dict[str, Any],
    *,
    name: str = "result",
    extra: list[Path] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    job = f"studio{abs(hash((op, json.dumps(options, sort_keys=True), name))) % 10**8}"
    request = {
        "job_id": job,
        "work_dir": str(workspace / ".work" / job),
        "source_path": str(source),
        "op": op,
        "options": options,
        "output_dir": str(workspace / "out"),
        "output_name": name,
        "extra_paths": [str(p) for p in extra or []],
    }
    (workspace / "out").mkdir(exist_ok=True)
    buffer = io.StringIO()
    studio_worker.OUT = buffer
    code = studio_worker.run(request)
    return code, [json.loads(line) for line in buffer.getvalue().splitlines()]


def outputs(events: list[dict[str, Any]]) -> list[Path]:
    done = [e for e in events if e["t"] == "done"]
    assert done, [e for e in events if e["t"] == "error"]
    return [Path(f) for f in done[-1]["files"]]


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_lossless_trim_keeps_codecs_and_the_requested_length(workspace: Path) -> None:
    source = workspace / "video_h264.mp4"
    before = digest(source)
    code, events = run_op(
        workspace, source, "trim", {"mode": "lossless", "segments": [{"start": 1.0, "end": 3.0}]}
    )
    assert code == 0
    [output] = outputs(events)
    assert output.name == "result.mp4"
    assert duration(output) == pytest.approx(2.0, abs=0.1)
    assert [s["codec_name"] for s in probe(output)["streams"]] == ["h264"]
    assert digest(source) == before  # the source is only ever read


def test_a_lossless_cut_off_a_keyframe_is_predicted_and_explained(workspace: Path) -> None:
    source = workspace / "video_h264.mp4"
    assert ops.keyframe_at_or_before(source, 1.5) == pytest.approx(1.0, abs=0.01)
    info = ops.probe_source(source)
    plan = ops.plan_trim(
        info,
        {"mode": "lossless", "segments": [{"start": 1.5, "end": 3.0}]},
        "out.mp4",
        "/tmp",
        keyframes={1.5: 1.0},
    )
    moved = [n for n in plan.notices if n["code"] == "CUT_MOVES_TO_KEYFRAME"]
    assert moved == [
        {
            "code": "CUT_MOVES_TO_KEYFRAME",
            "level": "warn",
            "params": {"requested": 1.5, "actual": 1.0},
        }
    ]


def test_frame_accurate_trim_reencodes_to_the_exact_length(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "video_h264.mp4",
        "trim",
        {"mode": "accurate", "segments": [{"start": 1.5, "end": 3.2}]},
    )
    assert code == 0
    [output] = outputs(events)
    assert duration(output) == pytest.approx(1.7, abs=0.05)
    assert probe(output)["streams"][0]["codec_name"] == "h264"


def test_several_segments_joined_losslessly(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "video_h264.mp4",
        "trim",
        {
            "mode": "lossless",
            "join": True,
            "segments": [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}],
        },
    )
    assert code == 0
    [output] = outputs(events)
    # Stream copy cannot split a group of frames: with B-frames each piece keeps a couple of
    # extra frames at its end (measured: 27 instead of 25 at 25 fps). Never shorter than asked,
    # and at most a few frames longer per piece -- the frame-accurate mode is the exact one.
    assert 2.0 <= duration(output) <= 2.0 + 2 * 0.12


def test_several_segments_joined_frame_accurately(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "video_h264.mp4",
        "trim",
        {
            "mode": "accurate",
            "join": True,
            "segments": [{"start": 0.5, "end": 1.2}, {"start": 2.5, "end": 3.0}],
        },
    )
    assert code == 0
    [output] = outputs(events)
    assert duration(output) == pytest.approx(1.2, abs=0.06)


def test_several_segments_as_separate_files(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "video_h264.mp4",
        "trim",
        {
            "mode": "lossless",
            "segments": [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 4.0}],
        },
    )
    assert code == 0
    files = outputs(events)
    assert [f.name for f in files] == ["result.1.mp4", "result.2.mp4"]
    assert [round(duration(f)) for f in files] == [1, 2]


def test_convert_audio_to_mp3_with_bitrate_and_mono(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "audio_en.m4a",
        "audio",
        {"codec": "mp3", "bitrate": "128", "channels": 1, "sample_rate": 22050},
    )
    assert code == 0
    [output] = outputs(events)
    [stream] = probe(output)["streams"]
    assert stream["codec_name"] == "mp3"
    assert int(stream["sample_rate"]) == 22050 and stream["channels"] == 1


def _integrated_loudness(path: Path) -> float:
    err = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    return float(json.loads(err[err.rindex("{") : err.rindex("}") + 1])["input_i"])


def test_loudness_normalisation_hits_the_ebu_r128_target(workspace: Path) -> None:
    source = workspace / "audio_en.m4a"
    assert abs(_integrated_loudness(source) - -16) > 2  # the tone starts well off target
    code, events = run_op(
        workspace, source, "audio", {"codec": "m4a", "bitrate": "192", "loudnorm": True}
    )
    assert code == 0, events[-1]
    [output] = outputs(events)
    assert _integrated_loudness(output) == pytest.approx(-16, abs=1.0)
    progress = [e["progress"] for e in events if e["t"] == "progress"]
    assert progress == sorted(progress) and progress[-1] == 1.0  # two passes, one bar


def test_remux_to_mp4_drops_a_track_sets_language_and_converts_subtitles(workspace: Path) -> None:
    multi = workspace / "multi.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(workspace / "video_h264.mp4"),
            "-i",
            str(workspace / "audio_en.m4a"),
            "-i",
            str(workspace / "audio_tr.m4a"),
            "-i",
            str(workspace / "sub_en.vtt"),
            "-map",
            "0",
            "-map",
            "1",
            "-map",
            "2",
            "-map",
            "3",
            "-c",
            "copy",
            "-c:s",
            "srt",
            str(multi),
        ],
        check=True,
    )
    info = ops.probe_source(multi)
    streams = {s["index"]: s for s in info["streams"]}
    tracks = [
        {"input": 0, "stream": 0, "keep": True},
        {"input": 0, "stream": 2, "keep": True, "language": "tr", "default": True},  # TR first
        {"input": 0, "stream": 1, "keep": False},  # EN dropped
        {"input": 0, "stream": 3, "keep": True, "language": "en"},
    ]
    assert streams[3]["codec"] == "subrip"
    code, events = run_op(workspace, multi, "remux", {"container": "mp4", "tracks": tracks})
    assert code == 0, events[-1]
    [output] = outputs(events)
    kinds = [
        (s["codec_type"], s["codec_name"], s.get("tags", {}).get("language"))
        for s in probe(output)["streams"]
    ]
    assert kinds == [
        ("video", "h264", "und"),
        ("audio", "aac", "tur"),
        ("subtitle", "mov_text", "eng"),
    ]


def test_remux_refuses_what_mp4_cannot_carry(workspace: Path) -> None:
    wav = workspace / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            str(wav),
        ],
        check=True,
    )
    plan = ops.plan_remux(ops.probe_source(wav), {"container": "mp4"}, "out.mp4")
    assert plan.blocking
    assert {n["code"] for n in plan.notices} >= {"CODEC_NOT_IN_MP4"}


def test_clean_youtube_auto_captions_to_srt(workspace: Path) -> None:
    vtt = workspace / "asr.en.vtt"
    vtt.write_text(YOUTUBE_ASR, encoding="utf-8")
    code, events = run_op(workspace, vtt, "subtitle", {"action": "clean", "target": "srt"})
    assert code == 0, events[-1]
    [output] = outputs(events)
    text = output.read_text()
    assert text.count("hello world this") == 1 and "<c>" not in text


def test_shift_subtitles_then_write_ass(workspace: Path) -> None:
    code, events = run_op(
        workspace,
        workspace / "sub_en.vtt",
        "subtitle",
        {"action": "shift", "offset": 1.5, "target": "ass"},
    )
    assert code == 0, events[-1]
    [output] = outputs(events)
    assert output.suffix == ".ass"
    assert "0:00:01.50" in output.read_text()  # the first cue started at 0.0


def test_studio_never_overwrites_an_existing_output(workspace: Path) -> None:
    options = {"codec": "mp3", "bitrate": "96"}
    run_op(workspace, workspace / "audio_en.m4a", "audio", options, name="same")
    _, second = run_op(
        workspace, workspace / "audio_en.m4a", "audio", {**options, "bitrate": "97"}, name="same"
    )
    assert [p.name for p in outputs(second)] == ["same (2).mp3"]


def test_a_non_media_source_is_refused(workspace: Path) -> None:
    text = workspace / "notes.txt"
    text.write_text("not a video")
    code, events = run_op(workspace, text, "audio", {"codec": "mp3"})
    assert code == 1
    assert events[-1]["code"] == "SOURCE_NOT_MEDIA"
