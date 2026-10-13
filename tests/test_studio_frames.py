"""Stüdyo cuts on exactly the frames Berk chose (2026-10-13): what is selected is what is cut.

The test clip is 25 fps with a moving picture, so neighbouring frames differ: the first frame of
a cut is compared with the source's frames around the chosen one and must match that one best.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.ffmpeg import binaries
from app.studio import ops
from tests.test_jobs_api import app_env, wait_for

__all__ = ["app_env"]


def _source(tmp_path: Path, test_media: Path) -> Path:
    folder = tmp_path / "Desktop"
    folder.mkdir()
    clip = folder / "clip.mp4"
    shutil.copy2(test_media / "video_h264.mp4", clip)
    return clip


def frame_count(path: Path) -> int:
    out = subprocess.run(
        [
            binaries.ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.strip().split(",")[0])


def thumb(path: Path, n: int) -> bytes:
    """Frame n, as 32x18 grey pixels."""
    return subprocess.run(
        [
            binaries.ffmpeg(),
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{n}),scale=32:18,format=gray",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


def distance(a: bytes, b: bytes) -> int:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True))


def run(client: Any, clip: Path, options: dict[str, Any], name: str) -> list[Path]:
    job = client.post(
        "/api/studio/jobs",
        json={"source_path": str(clip), "op": "trim", "output_name": name, "options": options},
    ).json()
    done = wait_for(client, job["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done["error_raw"]
    return [Path(p) for p in done["output_files"]]


def test_the_probe_knows_the_frame_grid_and_the_keyframes(tmp_path: Path, test_media: Path) -> None:
    clip = _source(tmp_path, test_media)
    source = ops.probe_source(clip)
    assert source["frame_rate"] == {"num": 25, "den": 1}
    assert source["variable_frame_rate"] is False
    assert ops.keyframes(clip) == [0.0, 1.0, 2.0, 3.0]


def test_a_frame_accurate_cut_keeps_exactly_the_chosen_frames(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    [output] = run(
        client,
        clip,
        {"mode": "accurate", "segments": [{"start_frame": 10, "end_frame": 35}]},
        "clip (kare 10-35)",
    )
    assert frame_count(output) == 25
    first = thumb(output, 0)
    scores = {n: distance(first, thumb(clip, n)) for n in (9, 10, 11)}
    assert min(scores, key=scores.__getitem__) == 10, scores
    last = thumb(output, 24)
    scores = {n: distance(last, thumb(clip, n)) for n in (33, 34, 35)}
    assert min(scores, key=scores.__getitem__) == 34, scores


def test_joined_frame_accurate_pieces_keep_exactly_their_frames(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    [output] = run(
        client,
        clip,
        {
            "mode": "accurate",
            "join": True,
            "segments": [{"start_frame": 5, "end_frame": 15}, {"start_frame": 60, "end_frame": 72}],
        },
        "clip (iki parça)",
    )
    assert frame_count(output) == 22
    second_piece = thumb(output, 10)
    scores = {n: distance(second_piece, thumb(clip, n)) for n in (59, 60, 61)}
    assert min(scores, key=scores.__getitem__) == 60, scores


def test_a_lossless_cut_from_a_keyframe_starts_on_that_frame(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    plan = client.post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "clip (kayıpsız)",
            "options": {"mode": "lossless", "segments": [{"start_frame": 25, "end_frame": 50}]},
        },
    ).json()
    # Chosen on the keyframe at 1 s: nothing moves, so no warning.
    assert not any(n["code"] == "CUT_MOVES_TO_KEYFRAME" for n in plan["notices"])
    [output] = run(
        client,
        clip,
        {"mode": "lossless", "segments": [{"start_frame": 25, "end_frame": 50}]},
        "clip (kayıpsız)",
    )
    first = thumb(output, 0)
    scores = {n: distance(first, thumb(clip, n)) for n in (24, 25, 26)}
    assert min(scores, key=scores.__getitem__) == 25, scores
    # A stream copy may end a few frames late (B-frames; gotcha 21), never early.
    assert 25 <= frame_count(output) <= 28


def test_frames_use_the_sources_own_rate_and_invalid_frames_block(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    plan = client.post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "x",
            "options": {"mode": "accurate", "segments": [{"start_frame": 30, "end_frame": 30}]},
        },
    ).json()
    assert plan["blocking"] and plan["notices"][0]["code"] == "INVALID_SEGMENT"
    plan = client.post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "x",
            "options": {"mode": "accurate", "segments": [{"start_frame": 10, "end_frame": 35}]},
        },
    ).json()
    command = plan["steps"][0]["command"]
    assert "-ss 0.399000" in command  # a millisecond before frame 10, at 0.4 s
    assert "-frames:v 25" in command and "-t 1.000000" in command


# ---- the playable preview -------------------------------------------------------------------
def wait_preview(client: Any, path: Path) -> dict[str, Any]:
    import time

    status: dict[str, Any] = {}
    for _ in range(600):
        status = client.post("/api/studio/preview/status", json={"path": str(path)}).json()
        if status["state"] in ("ready", "failed"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"preview never finished: {status}")


def test_a_preview_keeps_every_frame_where_it_was(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    for name in ("video_h264.mp4", "video_vp9.webm"):  # copied as is / re-encoded to H.264
        clip = tmp_path / name
        shutil.copy2(test_media / name, clip)
        assert (
            client.post("/api/studio/preview/status", json={"path": str(clip)}).json()["state"]
            == "none"
        )
        started = client.post("/api/studio/preview", json={"path": str(clip)}).json()
        assert started["state"] in ("running", "ready")
        status = wait_preview(client, clip)
        assert status["state"] == "ready", status
        preview = Path(status["path"])
        assert preview.suffix == ".mp4" and preview.parent.name == "preview-cache"
        # In the app's data folder, never next to Berk's file.
        from app import paths

        assert preview.parent == paths.data_dir() / "preview-cache" != clip.parent
        assert frame_count(preview) == frame_count(clip)
        probe = ops.probe_source(preview)
        codecs = {s["type"]: s["codec"] for s in probe["streams"]}
        assert codecs["video"] == "h264"
        # Frame 30 of the preview is frame 30 of the source.
        scores = {n: distance(thumb(preview, 30), thumb(clip, n)) for n in (29, 30, 31)}
        assert min(scores, key=scores.__getitem__) == 30, (name, scores)
        # Asked again: the same file, from the cache.
        again = client.post("/api/studio/preview", json={"path": str(clip)}).json()
        assert again["state"] == "ready" and again["path"] == status["path"]


def test_keyframes_and_previews_refuse_what_is_not_a_media_file(
    app_env: Any, tmp_path: Path
) -> None:
    client = app_env()
    note = tmp_path / "note.txt"
    note.write_text("hello")
    assert (
        client.post("/api/studio/preview", json={"path": str(note)}).json()["error"]["code"]
        == "SOURCE_NOT_MEDIA"
    )
    assert client.post("/api/studio/keyframes", json={"path": "/nope"}).status_code == 404
    assert client.post("/api/studio/preview", json={"path": "relative.mp4"}).status_code == 404


# ---- awkward sources (review of N7) ---------------------------------------------------------
def _make(tmp_path: Path, test_media: Path, name: str, *argv: str) -> Path:
    out = tmp_path / name
    subprocess.run(
        [binaries.ffmpeg(), "-v", "error", "-y", *argv, str(out)],
        check=True,
        cwd=test_media,
    )
    return out


def _stream_start(path: Path, kind: str) -> float:
    out = subprocess.run(
        [
            binaries.ffprobe(),
            "-v",
            "error",
            "-select_streams",
            kind,
            "-show_entries",
            "stream=start_time",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(out.strip().splitlines()[0])


def _first_is(output: Path, source: Path, frame: int, at: int = 0) -> None:
    got = thumb(output, at)
    scores = {n: distance(got, thumb(source, n)) for n in (frame - 1, frame, frame + 1)}
    assert min(scores, key=scores.__getitem__) == frame, scores


def test_frames_count_from_the_videos_own_first_frame(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    """Video starting 63 ms after the sound: frame 10 is still the video's tenth frame, and the
    picture and the sound of the cut start together."""
    clip = _make(
        tmp_path,
        test_media,
        "late-video.mkv",
        *("-i", "audio_en.m4a", "-itsoffset", "0.063", "-i", "video_h264.mp4"),
        *("-map", "1:v", "-map", "0:a", "-c", "copy"),
    )
    source = ops.probe_source(clip)
    assert abs(source["video_start"] - 0.063) < 0.002
    client = app_env()
    [single] = run(
        client, clip, {"mode": "accurate", "segments": [{"start_frame": 10, "end_frame": 40}]}, "a"
    )
    assert frame_count(single) == 30
    _first_is(single, clip, 10)
    assert abs(_stream_start(single, "v:0") - _stream_start(single, "a:0")) <= 0.021
    [joined] = run(
        client,
        clip,
        {
            "mode": "accurate",
            "join": True,
            "segments": [
                {"start_frame": 10, "end_frame": 20},
                {"start_frame": 50, "end_frame": 60},
            ],
        },
        "b",
    )
    assert frame_count(joined) == 20
    _first_is(joined, clip, 10)
    _first_is(joined, clip, 50, at=10)
    # Keyframes are counted from the same first frame (the clip has one each second).
    assert ops.keyframes(clip) == [0.0, 1.0, 2.0, 3.0]


def test_an_mpeg_ts_source_is_cut_on_the_chosen_frames(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    clip = _make(
        tmp_path,
        test_media,
        "broadcast.ts",
        *("-i", "video_h264.mp4", "-i", "audio_en.m4a", "-map", "0:v", "-map", "1:a"),
        *("-c", "copy", "-f", "mpegts"),
    )
    [output] = run(
        app_env(),
        clip,
        {"mode": "accurate", "segments": [{"start_frame": 60, "end_frame": 90}]},
        "c",
    )
    assert frame_count(output) == 30
    _first_is(output, clip, 60)


def test_a_variable_frame_rate_source_is_cut_by_time_not_by_frame_numbers(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    """40 fps for a second, then 20: "frame N" of a nominal rate is no real frame there, so the
    source offers no frame grid and frame numbers are refused; times cut exactly."""
    clip = _make(
        tmp_path,
        test_media,
        "variable.mp4",
        *("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=40", "-t", "3"),
        *("-vf", "select='lt(n\\,40)+not(mod(n\\,2))'", "-fps_mode", "vfr", "-c:v", "libx264"),
    )
    source = ops.probe_source(clip)
    assert source["variable_frame_rate"] is True and source["frame_rate"] is None
    client = app_env()
    plan = client.post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "x",
            "options": {"mode": "accurate", "segments": [{"start_frame": 10, "end_frame": 20}]},
        },
    ).json()
    assert plan["blocking"]
    [output] = run(
        client, clip, {"mode": "accurate", "segments": [{"start": 1.0, "end": 2.0}]}, "d"
    )
    assert frame_count(output) == 20  # one second at 20 fps


def test_a_preview_removed_from_the_cache_is_made_again(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = tmp_path / "clip.webm"
    shutil.copy2(test_media / "video_vp9.webm", clip)
    client.post("/api/studio/preview", json={"path": str(clip)})
    first = wait_preview(client, clip)
    Path(first["path"]).unlink()  # evicted by the size cap, or deleted by hand
    status = client.post("/api/studio/preview/status", json={"path": str(clip)}).json()
    assert status["state"] == "none"
    client.post("/api/studio/preview", json={"path": str(clip)})
    assert Path(wait_preview(client, clip)["path"]).is_file()


def test_mp3_sound_is_previewed_as_aac(app_env: Any, tmp_path: Path, test_media: Path) -> None:
    """An .m4a cannot carry MP3 (the muxer refuses it): the preview re-encodes it."""
    clip = _make(
        tmp_path, test_media, "song.mka", "-i", "audio_en.m4a", "-c:a", "libmp3lame", "-q:a", "5"
    )
    client = app_env()
    client.post("/api/studio/preview", json={"path": str(clip)})
    status = wait_preview(client, clip)
    assert status["state"] == "ready", status
    codecs = {s["type"]: s["codec"] for s in ops.probe_source(Path(status["path"]))["streams"]}
    assert codecs == {"audio": "aac"}


def test_asking_about_a_path_needs_a_post(app_env: Any, tmp_path: Path) -> None:
    """A GET is not checked for its origin, so no GET names a local file."""
    response = app_env().get("/api/studio/preview", params={"path": str(tmp_path)})
    assert response.status_code in (404, 405)
    assert "state" not in response.text
