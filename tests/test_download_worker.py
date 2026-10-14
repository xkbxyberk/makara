"""The real yt-dlp + FFmpeg pipeline, end to end, against media served on 127.0.0.1.

Every assertion about the output file is made with ffprobe, not by trusting our own code.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.ffmpeg.probe import probe
from app.settings import DEFAULT_TEMPLATE
from app.workers import download_worker

AUDIO_TRACKS = [
    {"format_id": "a-en-m4a", "language": "en", "role": "original"},
    {"format_id": "a-en-opus", "language": "en", "role": "original"},
    {"format_id": "a-tr-m4a", "language": "tr", "role": "dub"},
    {"format_id": "a-de-m4a", "language": "de", "role": "dub"},
]
SUB_TRACKS = [{"key": k, "language": k} for k in ("en", "tr", "de")]


def run_job(
    tmp_path: Path, info: dict[str, Any], **overrides: Any
) -> tuple[int, list[dict[str, Any]]]:
    job_id = "job" + str(abs(hash(json.dumps(overrides, sort_keys=True))))[:8]
    request = {
        "job_id": job_id,
        "download_dir": str(tmp_path / "out"),
        "work_dir": str(tmp_path / "out" / ".vd-work" / job_id),
        "filename_template": DEFAULT_TEMPLATE,
        "info": info,
        "audio_tracks": AUDIO_TRACKS,
        "subtitle_tracks": SUB_TRACKS,
        "expected_sizes": {},
        "extras": {"thumbnail": True},
        "subtitle_keys": [],
        "audio_format_ids": [],
        "video_format_id": None,
        **overrides,
    }
    buffer = io.StringIO()
    download_worker.OUT = buffer
    code = download_worker.run(request)
    events = [json.loads(line) for line in buffer.getvalue().splitlines()]
    return code, events


def done_files(events: list[dict[str, Any]]) -> list[Path]:
    done = [e for e in events if e["t"] == "done"]
    assert done, f"job did not finish: {[e for e in events if e['t'] == 'error']}"
    return [Path(f) for f in done[-1]["files"]]


def streams(path: Path, kind: str) -> list[dict[str, Any]]:
    """Streams of one type. Cover art is reported separately (see `cover_art`)."""
    return [
        s
        for s in probe(path)["streams"]
        if s["codec_type"] == kind and not s.get("disposition", {}).get("attached_pic")
    ]


def cover_art(path: Path) -> list[dict[str, Any]]:
    # Matroska's demuxer surfaces an attachment named cover.* as an attached-picture stream,
    # which is exactly what makes players show it.
    return [s for s in probe(path)["streams"] if s.get("disposition", {}).get("attached_pic")]


def test_archive_mkv_with_two_audio_languages_and_two_subtitles(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="mkv",
        video_format_id="v-vp9",
        audio_format_ids=["a-en-opus", "a-tr-m4a"],
        subtitle_keys=["en", "tr"],
    )
    assert code == 0
    [output] = done_files(events)
    assert output.name == "2026-09-01 - Local test clip [localclip01].mkv"
    assert output.parent.name == "VD Test Channel"

    info = probe(output)
    video = streams(output, "video")
    assert [v["codec_name"] for v in video] == ["vp9"]
    audio = streams(output, "audio")
    assert [a["tags"]["language"] for a in audio] == ["eng", "tur"]
    assert [a["disposition"]["default"] for a in audio] == [1, 0]
    assert [a["codec_name"] for a in audio] == ["opus", "aac"]  # copied, never re-encoded
    subs = streams(output, "subtitle")
    assert [s["tags"]["language"] for s in subs] == ["eng", "tur"]
    assert all(s["disposition"]["default"] == 0 for s in subs)
    [cover] = cover_art(output)
    assert cover["codec_name"] == "mjpeg"
    assert [c["tags"]["title"] for c in info["chapters"]] == ["Intro", "Outro"]
    assert float(info["format"]["duration"]) == pytest.approx(4, abs=0.3)

    stages = [e["stage"] for e in events if e["t"] == "stage"]
    assert "downloading" in stages and "merging" in stages
    progress = [
        e["progress"] for e in events if e["t"] == "progress" and e["stage"] == "downloading"
    ]
    assert progress == sorted(progress) and progress[-1] == 1.0
    # The scratch directory is gone once the file is in place.
    assert list((tmp_path / "out" / ".vd-work").iterdir()) == []
    thumbnail = next(e for e in events if e["t"] == "done")["outputs"][0]["thumbnail"]
    assert thumbnail and Path(thumbnail).stat().st_size > 0  # a frame from the video


def test_compat_mp4_reencodes_only_what_quicktime_cannot_play(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="compat_mp4",
        video_format_id="v-vp9",
        audio_format_ids=["a-en-opus"],
        subtitle_keys=["en"],
    )
    assert code == 0
    [output] = done_files(events)
    assert output.suffix == ".mp4"
    [video] = streams(output, "video")
    assert video["codec_name"] == "h264" and video["codec_tag_string"] == "avc1"
    assert len(cover_art(output)) == 1
    [audio] = streams(output, "audio")
    assert audio["codec_name"] == "aac"
    assert [s["codec_name"] for s in streams(output, "subtitle")] == ["mov_text"]
    assert "converting" in [e["stage"] for e in events if e["t"] == "stage"]
    plan = next(e for e in events if e["t"] == "done")["plan"]
    assert plan["video"][0].startswith("transcode:vp9")


def test_compat_mp4_copies_when_already_compatible(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="compat_mp4",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a"],
    )
    assert code == 0
    [output] = done_files(events)
    plan = next(e for e in events if e["t"] == "done")["plan"]
    assert plan == {"video": ["copy:h264"], "audio": ["copy:aac"], "subtitle": []}
    assert "converting" not in [e["stage"] for e in events if e["t"] == "stage"]
    assert streams(output, "video")[0]["codec_tag_string"] == "avc1"


def test_audio_only_mp3_with_cover_art_and_metadata(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="audio",
        audio_format_ids=["a-en-opus"],
        audio_codec="mp3",
        audio_quality="192",
    )
    assert code == 0
    [output] = done_files(events)
    assert output.suffix == ".mp3"
    info = probe(output)
    assert [a["codec_name"] for a in streams(output, "audio")] == ["mp3"]
    assert len(cover_art(output)) == 1
    assert info["format"]["tags"]["title"] == "Local test clip"
    # The library grid shows the embedded cover.
    done = next(e for e in events if e["t"] == "done")
    thumbnail = done["outputs"][0]["thumbnail"]
    assert thumbnail and Path(thumbnail).stat().st_size > 0


def test_separate_files_are_named_for_players_to_autoload(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="separate",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a", "a-tr-m4a"],
        subtitle_keys=["tr"],
        extras={"thumbnail_file": True},
    )
    assert code == 0
    names = sorted(p.name for p in done_files(events))
    stem = "2026-09-01 - Local test clip [localclip01]"
    assert names == sorted(
        [
            f"{stem}.mp4",
            f"{stem}.en.m4a",
            f"{stem}.tr.m4a",
            f"{stem}.tr.srt",
            f"{stem}.jpg",
        ]
    )


def test_an_existing_file_is_never_overwritten(tmp_path: Path, local_info: dict[str, Any]) -> None:
    kwargs = {"mode": "audio", "audio_format_ids": ["a-en-m4a"], "audio_codec": "m4a"}
    _, first = run_job(tmp_path, local_info, **kwargs)
    _, second = run_job(tmp_path, local_info, **{**kwargs, "audio_quality": "1"})
    [a], [b] = done_files(first), done_files(second)
    assert a != b and b.name.endswith(" (2).m4a")
    assert a.exists() and b.exists()


def test_a_template_escaping_the_download_root_is_refused(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="audio",
        audio_format_ids=["a-en-m4a"],
        audio_codec="m4a",
        filename_template="../../escape/%(title)s.%(ext)s",
    )
    assert code == 1
    assert events[-1] == {"t": "error", "code": "PATH_OUTSIDE_ROOT", "raw": events[-1]["raw"]}
    assert not (tmp_path / "escape").exists()


def test_an_unreachable_stream_fails_with_a_code(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    broken = json.loads(json.dumps(local_info))
    for fmt in broken["formats"]:
        fmt["url"] = "http://127.0.0.1:1/gone.mp4"
    code, events = run_job(
        tmp_path, broken, mode="mkv", video_format_id="v-h264", audio_format_ids=["a-en-m4a"]
    )
    assert code == 1
    assert events[-1]["t"] == "error" and events[-1]["code"] == "NETWORK"


def test_a_title_of_dot_dot_cannot_escape_the_download_folder(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    hostile = {**local_info, "title": ".."}
    code, events = run_job(
        tmp_path,
        hostile,
        mode="audio",
        audio_format_ids=["a-en-m4a"],
        audio_codec="m4a",
        filename_template="%(channel)s/%(title)s.%(ext)s",
    )
    assert code == 0, events[-1]
    [output] = done_files(events)
    root = (tmp_path / "out").resolve()
    assert output.resolve().is_relative_to(root) and output.resolve().parent != root.parent
    assert not (tmp_path / "out.m4a").exists()


def test_a_very_long_title_still_downloads(tmp_path: Path, local_info: dict[str, Any]) -> None:
    long = {**local_info, "title": "Çok uzun başlık " * 40}
    code, events = run_job(
        tmp_path,
        long,
        mode="audio",
        audio_format_ids=["a-en-m4a"],
        audio_codec="m4a",
        extras={"description": True},
    )
    assert code == 0, events[-1]
    assert all(len(p.name.encode()) <= 255 for p in done_files(events))


def test_repeating_separate_files_keeps_one_matching_base_name(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    kwargs = {
        "mode": "separate",
        "video_format_id": "v-h264",
        "audio_format_ids": ["a-tr-m4a"],
        "subtitle_keys": ["tr"],
    }
    run_job(tmp_path, local_info, **kwargs)
    _, second = run_job(tmp_path, local_info, **{**kwargs, "audio_quality": "1"})
    stem = "2026-09-01 - Local test clip [localclip01] (2)"
    assert sorted(p.name for p in done_files(second)) == sorted(
        [f"{stem}.mp4", f"{stem}.tr.m4a", f"{stem}.tr.srt"]
    )


def test_audio_mode_can_also_keep_the_cover_as_a_file(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="audio",
        audio_format_ids=["a-en-m4a"],
        audio_codec="m4a",
        extras={"thumbnail": True, "thumbnail_file": True},
    )
    assert code == 0
    files = done_files(events)
    assert [p.suffix for p in files] == [".m4a", ".jpg"]
    assert len(cover_art(files[0])) == 1  # embedded *and* kept


def test_an_unreadable_subtitle_is_skipped_with_a_warning_not_a_failed_job(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    code, events = run_job(
        tmp_path,
        local_info,
        mode="mkv",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a"],
        subtitle_keys=["ja", "tr"],
    )
    assert code == 0, events[-1]
    done = next(e for e in events if e["t"] == "done")
    assert done["warnings"] == [{"code": "SUBTITLE_SKIPPED", "key": "ja"}]
    [output] = done_files(events)
    assert [s["tags"]["language"] for s in streams(output, "subtitle")] == ["tur"]


def test_a_transient_403_is_retried_once_with_a_fresh_pass(
    tmp_path: Path, local_info: dict[str, Any], media_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download_worker, "FORBIDDEN_RETRY_DELAY", 0.0)
    flaky = json.loads(json.dumps(local_info).replace(media_server, f"{media_server}/flaky403"))
    code, events = run_job(
        tmp_path,
        flaky,
        mode="audio",
        audio_format_ids=["a-en-m4a"],
        audio_codec="m4a",
        extras={"thumbnail": False},
    )
    assert code == 0, events[-1]
    assert {"t": "stage", "stage": "retrying"} in events


def test_a_single_file_format_downloads_through_aria2c_with_progress(
    tmp_path: Path,
    local_info: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Several connections via aria2c (P2). Its output must not reach the worker's stdout, which
    carries the JSON protocol, and its readout must become progress events."""
    from app.workers import aria2

    calls: list[list[str]] = []
    real = aria2._call_process

    def counting(self: Any, cmd: list[str], info_dict: dict[str, Any]) -> tuple[str, str, int]:
        calls.append(cmd)
        return real(self, cmd, info_dict)

    monkeypatch.setattr(aria2, "_call_process", counting)
    code, events = run_job(
        tmp_path,
        local_info,
        mode="compat_mp4",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a"],
        network={"connections": 4, "rate_limit": None, "aria2c": "/opt/homebrew/bin/aria2c"},
    )
    assert code == 0, [e for e in events if e["t"] == "error"]
    [output] = done_files(events)
    assert streams(output, "video") and streams(output, "audio")
    assert len(calls) == 2  # the video and the audio, each its own aria2c run
    assert all("-x" in cmd and cmd[cmd.index("-x") + 1] == "4" for cmd in calls)
    assert any(e["t"] == "progress" for e in events)
    # The segment map: every progress event says how the file is fetched; the last is complete.
    maps = [e for e in events if e["t"] == "progress" and e.get("pieces")]
    assert maps and maps[-1]["pieces"] == "9" * aria2.CELLS
    assert "aria2" not in capfd.readouterr().out.lower()


def test_the_safari_session_never_goes_to_aria2c() -> None:
    options = download_worker._network_params(
        {
            "network": {"connections": 8, "rate_limit": 2_000_000, "aria2c": "/x/aria2c"},
            "cookies_from_browser": ["safari", "/x/Cookies.binarycookies"],
        }
    )
    assert "external_downloader" not in options
    # A cap is exact: one fragment at a time, at the cap.
    assert options == {"concurrent_fragment_downloads": 1, "ratelimit": 2_000_000}


def test_finder_says_where_the_file_came_from(tmp_path: Path, local_info: dict[str, Any]) -> None:
    from app import finder

    code, events = run_job(
        tmp_path,
        local_info,
        mode="compat_mp4",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a"],
    )
    assert code == 0
    [output] = done_files(events)
    assert finder.where_from(output) == [local_info["webpage_url"]]


def test_the_segment_map_comes_from_aria2cs_control_file() -> None:
    """A real `.aria2` captured mid-download (30 MB, 1 MiB pieces, 8 connections)."""
    from app.workers import aria2

    cells = aria2.pieces(Path(__file__).parent / "fixtures" / "sample.aria2")
    assert cells is not None and len(cells) == aria2.CELLS
    assert set(cells) - set("0123456789") == set()
    # Pieces 0, 4, 8, ... were done (bitfield 88 89 12 20): finished cells and empty ones both.
    assert "9" in cells and "0" in cells
    assert aria2.pieces(Path("/nonexistent.aria2")) is None


def test_a_server_that_refuses_aria2c_still_gets_the_download(
    tmp_path: Path, local_info: dict[str, Any]
) -> None:
    """Some hosts refuse several connections to one file: when aria2c fails, the same pass
    runs once more with yt-dlp's own downloader, and the job still finishes."""
    fake = tmp_path / "aria2c"
    # Answers the availability check (`aria2c -v`), then fails every download.
    fake.write_text(
        '#!/bin/sh\n[ "$1" = "-v" ] && { echo "aria2 version 1.37.0"; exit 0; }\nexit 22\n'
    )
    fake.chmod(0o755)
    code, events = run_job(
        tmp_path,
        local_info,
        mode="compat_mp4",
        video_format_id="v-h264",
        audio_format_ids=["a-en-m4a"],
        network={"connections": 4, "rate_limit": None, "aria2c": str(fake)},
    )
    assert code == 0, [e for e in events if e["t"] == "error"]
    assert done_files(events)
    assert "retrying" in [e["stage"] for e in events if e["t"] == "stage"]


@pytest.mark.parametrize(
    ("cover", "skipped"),
    [
        ("misnamed", False),  # a JPEG served as .png, as Reddit does: converted by its content
        ("broken", True),  # not an image at all: the video is kept, without a cover
    ],
)
def test_a_bad_cover_never_costs_the_download(
    tmp_path: Path, local_info: dict[str, Any], test_media: Path, cover: str, skipped: bool
) -> None:
    name = f"cover-{cover}.png"
    if cover == "misnamed":
        shutil.copy2(test_media / "thumb.jpg", test_media / name)
    else:
        (test_media / name).write_bytes(b"<html>not an image</html>")
    base = local_info["thumbnails"][0]["url"].rsplit("/", 1)[0]
    info = {
        **local_info,
        "thumbnail": f"{base}/{name}",
        "thumbnails": [{"id": "0", "url": f"{base}/{name}"}],
    }
    code, events = run_job(
        tmp_path, info, mode="compat_mp4", video_format_id="v-h264", audio_format_ids=["a-en-m4a"]
    )
    assert code == 0, [e for e in events if e["t"] == "error"]
    [output] = done_files(events)
    warnings = next(e for e in events if e["t"] == "done")["warnings"]
    assert ({"code": "THUMBNAIL_SKIPPED"} in warnings) is skipped
    assert bool(cover_art(output)) is not skipped
