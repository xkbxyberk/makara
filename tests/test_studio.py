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

from app import errors
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


def test_probe_recognises_youtube_auto_captions(workspace: Path) -> None:
    vtt = workspace / "asr.vtt"
    vtt.write_text(YOUTUBE_ASR, encoding="utf-8")
    assert ops.probe_source(vtt)["youtube_auto_captions"] is True
    assert ops.probe_source(workspace / "sub_en.vtt")["youtube_auto_captions"] is False


# ---- regression tests for the M4 adversarial review ----------------------------------------


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def test_keyframe_prediction_inside_the_first_group_of_pictures(workspace: Path) -> None:
    # ffprobe prints the first keyframe as "0.000000," -- it must still count.
    assert ops.keyframe_at_or_before(workspace / "video_h264.mp4", 0.5) == pytest.approx(0.0)


def test_cover_art_is_not_mistaken_for_video(workspace: Path) -> None:
    song = workspace / "song.m4a"
    _ffmpeg(
        "-i",
        str(workspace / "audio_en.m4a"),
        "-i",
        str(Path(__file__).parent / "fixtures" / "media" / "thumb.jpg"),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "-disposition:v",
        "attached_pic",
        str(song),
    )
    # Audio cuts at packet granularity: nothing moves, so there is nothing to warn about.
    assert ops.keyframe_at_or_before(song, 1.5) == 1.5


def test_long_groups_of_pictures_are_still_found(workspace: Path) -> None:
    long_gop = workspace / "long_gop.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x64:rate=25:duration=32",
        "-c:v",
        "libx264",
        "-g",
        "1000",
        "-keyint_min",
        "1000",
        "-sc_threshold",
        "0",
        str(long_gop),
    )
    assert ops.keyframe_at_or_before(long_gop, 25.0) == pytest.approx(0.0)


def test_a_non_zero_start_time_is_accounted_for(workspace: Path) -> None:
    ts = workspace / "offset.ts"
    _ffmpeg(
        "-i", str(workspace / "video_h264.mp4"), "-c", "copy", "-output_ts_offset", "10", str(ts)
    )
    assert ops.keyframe_at_or_before(ts, 1.5) == pytest.approx(1.0, abs=0.05)


def test_an_empty_output_is_an_error_not_a_success(tmp_path: Path) -> None:
    empty = tmp_path / "output.mp4"
    empty.write_bytes(b"")
    with pytest.raises(errors.AppError) as caught:
        studio_worker._verify([empty])
    assert caught.value.code == "OUTPUT_EMPTY"


def test_joining_a_file_with_cover_art_losslessly(workspace: Path) -> None:
    song = workspace / "song.m4a"
    _ffmpeg(
        "-i",
        str(workspace / "audio_en.m4a"),
        "-i",
        str(Path(__file__).parent / "fixtures" / "media" / "thumb.jpg"),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "-disposition:v",
        "attached_pic",
        str(song),
    )
    code, events = run_op(
        workspace,
        song,
        "trim",
        {
            "mode": "lossless",
            "join": True,
            "segments": [{"start": 0, "end": 1}, {"start": 2, "end": 3}],
        },
    )
    assert code == 0, events[-1]
    [output] = outputs(events)
    kinds = [s["codec_type"] for s in probe(output)["streams"]]
    assert kinds == ["audio"]  # the cover does not turn into a video track


def test_failed_work_leaves_no_scratch_next_to_the_source(workspace: Path) -> None:
    code, events = run_op(
        workspace, workspace / "audio_en.m4a", "audio", {"codec": "mp3", "sample_rate": 1}
    )
    assert code == 1 and events[-1]["code"] == "FFMPEG_FAILED"
    assert not (workspace / "out" / ".vd-work").exists()
    assert list((workspace / "out").iterdir()) == []


def test_legacy_turkish_srt_is_shifted_and_converted_without_mojibake(workspace: Path) -> None:
    legacy = workspace / "eski.srt"
    legacy.write_bytes("1\r\n00:00:01,000 --> 00:00:02,000\r\nŞişli'de ığdır\r\n".encode("cp1254"))
    assert ops.probe_source(legacy)["charset"] == "CP1254"
    code, events = run_op(
        workspace,
        legacy,
        "subtitle",
        {"action": "shift", "offset": 1, "target": "srt"},
        name="shifted",
    )
    assert code == 0, events[-1]
    assert "Şişli'de ığdır" in outputs(events)[0].read_text(encoding="utf-8")
    code, events = run_op(
        workspace, legacy, "subtitle", {"action": "convert", "target": "ass"}, name="converted"
    )
    assert code == 0, events[-1]
    assert "Şişli'de ığdır" in outputs(events)[0].read_text(encoding="utf-8")


def test_opus_at_44_1_khz_becomes_48_khz(workspace: Path) -> None:
    code, events = run_op(
        workspace, workspace / "audio_en.m4a", "audio", {"codec": "opus", "sample_rate": 44100}
    )
    assert code == 0, events[-1]
    [stream] = probe(outputs(events)[0])["streams"]
    assert int(stream["sample_rate"]) == 48000


def test_a_slash_in_the_output_name_is_not_a_folder(workspace: Path) -> None:
    code, events = run_op(
        workspace, workspace / "audio_en.m4a", "audio", {"codec": "mp3"}, name="AC/DC - Live"
    )
    assert code == 0, events[-1]
    [output] = outputs(events)
    assert output.parent == (workspace / "out").resolve()
    assert output.name == "AC" + chr(0x29F8) + "DC - Live.mp3"  # BIG SOLIDUS, not a path


def test_remux_follows_the_track_order_and_flags(workspace: Path) -> None:
    multi = workspace / "multi.mkv"
    _ffmpeg(
        "-i",
        str(workspace / "video_h264.mp4"),
        "-i",
        str(workspace / "audio_en.m4a"),
        "-i",
        str(workspace / "audio_tr.m4a"),
        "-map",
        "0",
        "-map",
        "1",
        "-map",
        "2",
        "-c",
        "copy",
        "-metadata:s:a:0",
        "language=eng",
        "-metadata:s:a:1",
        "language=tur",
        str(multi),
    )
    tracks = [
        {"input": 0, "stream": 0, "keep": True},
        {"input": 0, "stream": 2, "keep": True, "language": "tr", "default": True},
        {"input": 0, "stream": 1, "keep": True, "language": "", "default": False},  # cleared
    ]
    code, events = run_op(workspace, multi, "remux", {"container": "mkv", "tracks": tracks})
    assert code == 0, events[-1]
    audio = [s for s in probe(outputs(events)[0])["streams"] if s["codec_type"] == "audio"]
    assert [s["tags"].get("language", "und") for s in audio] == ["tur", "und"]
    assert [s["disposition"]["default"] for s in audio] == [1, 0]


def test_remux_rejects_a_track_that_does_not_exist(workspace: Path) -> None:
    info = ops.probe_source(workspace / "video_h264.mp4")
    for bad in ({"input": 0, "stream": 7, "keep": True}, {"input": -1, "stream": 0, "keep": True}):
        plan = ops.plan_remux(info, {"container": "mkv", "tracks": [bad]}, "out.mkv")
        assert plan.blocking and "UNKNOWN_TRACK" in {n["code"] for n in plan.notices}


def test_remux_keeps_mkv_font_attachments(workspace: Path) -> None:
    (workspace / "font.ttf").write_bytes(b"\x00\x01\x00\x00" + bytes(252))  # stands in for a font
    with_font = workspace / "with_font.mkv"
    _ffmpeg(
        "-i",
        str(workspace / "video_h264.mp4"),
        "-attach",
        str(workspace / "font.ttf"),
        "-metadata:s:t",
        "mimetype=font/ttf",
        "-c",
        "copy",
        str(with_font),
    )
    code, events = run_op(workspace, with_font, "remux", {"container": "mkv"})
    assert code == 0, events[-1]
    kinds = [s["codec_type"] for s in probe(outputs(events)[0])["streams"]]
    assert "attachment" in kinds


def test_silent_audio_cannot_be_loudness_normalised(workspace: Path) -> None:
    silence = workspace / "silence.m4a"
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", "-c:a", "aac", str(silence))
    code, events = run_op(workspace, silence, "audio", {"codec": "mp3", "loudnorm": True})
    assert code == 1 and events[-1]["code"] == "LOUDNESS_SILENT"


def test_frame_accurate_cut_of_an_mp3_stays_mp3(workspace: Path) -> None:
    mp3 = workspace / "tone.mp3"
    _ffmpeg("-i", str(workspace / "audio_en.m4a"), "-c:a", "libmp3lame", str(mp3))
    code, events = run_op(
        workspace, mp3, "trim", {"mode": "accurate", "segments": [{"start": 1, "end": 2.5}]}
    )
    assert code == 0, events[-1]
    [output] = outputs(events)
    assert output.suffix == ".mp3"
    assert probe(output)["streams"][0]["codec_name"] == "mp3"


def test_malformed_options_are_a_coded_error() -> None:
    info = {
        "streams": [{"index": 0, "type": "audio", "codec": "aac", "attached_pic": False}],
        "path": "/x.m4a",
        "ext": "m4a",
        "duration": 4.0,
    }
    with pytest.raises(errors.AppError) as caught:
        ops.plan_audio(info, {"codec": "mp3", "bitrate": "loud"}, "out.mp3")
    assert caught.value.code == "INVALID_OPTION"
