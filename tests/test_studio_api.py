"""Studio through HTTP: probe, preview the exact plan, queue, and find the result."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from app.ffmpeg.probe import probe
from tests.test_jobs_api import app_env, wait_for

__all__ = ["app_env"]


def _source(tmp_path: Path, test_media: Path) -> Path:
    folder = tmp_path / "Desktop"
    folder.mkdir()
    clip = folder / "clip.mp4"
    shutil.copy2(test_media / "video_h264.mp4", clip)
    return clip


def test_probe_describes_a_local_file(app_env: Any, tmp_path: Path, test_media: Path) -> None:
    clip = _source(tmp_path, test_media)
    body = app_env().post("/api/studio/probe", json={"path": str(clip)}).json()
    assert body["duration"] > 3.9
    assert [s["codec"] for s in body["streams"]] == ["h264"]


def test_probe_refuses_what_is_not_media(app_env: Any, tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("hello")
    response = app_env().post("/api/studio/probe", json={"path": str(note)})
    assert response.json()["error"]["code"] == "SOURCE_NOT_MEDIA"


def test_plan_shows_the_exact_command_and_the_keyframe_shift(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    clip = _source(tmp_path, test_media)
    plan = (
        app_env()
        .post(
            "/api/studio/plan",
            json={
                "source_path": str(clip),
                "op": "trim",
                "output_name": "clip (kesit)",
                "options": {"mode": "lossless", "segments": [{"start": 1.5, "end": 3.0}]},
            },
        )
        .json()
    )
    [step] = plan["steps"]
    assert "-c copy" in step["command"] and "-ss 1.500" in step["command"]
    assert plan["outputs"] == [f"{clip.parent.resolve()}/clip (kesit).mp4"]
    shift = next(n for n in plan["notices"] if n["code"] == "CUT_MOVES_TO_KEYFRAME")
    assert shift["params"] == {"requested": 1.5, "actual": 1.0}


def test_a_studio_job_writes_next_to_the_source_and_joins_the_library(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    job = client.post(
        "/api/studio/jobs",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "clip (kesit)",
            "options": {"mode": "accurate", "segments": [{"start": 1.0, "end": 2.5}]},
        },
    ).json()
    assert job["mode"] == "studio"
    done = wait_for(client, job["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done["error_raw"]
    [output] = [Path(p) for p in done["output_files"]]
    assert output.parent == clip.parent.resolve() and output.name == "clip (kesit).mp4"
    # Frame-accurate: within one frame (0.04 s at 25 fps; the container counts the last frame).
    assert abs(float(probe(output)["format"]["duration"]) - 1.5) <= 0.041
    assert not (clip.parent / ".vd-work").exists()  # no scratch left next to Berk's file
    # The queue's "Finder'da göster" works for it (it once read a download-only key: HTTP 500).
    reveal = client.post(f"/api/jobs/{job['id']}/reveal", json={"index": 0})
    assert reveal.status_code == 200, reveal.text
    items = []
    for _ in range(50):
        items = client.get("/api/library").json()["items"]
        if items:
            break
        time.sleep(0.05)
    assert [i["mode"] for i in items] == ["studio"]


def test_output_may_only_go_next_to_the_source_or_the_download_folder(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    clip = _source(tmp_path, test_media)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    response = app_env().post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "audio",
            "output_name": "x",
            "options": {"codec": "mp3"},
            "output_dir": str(elsewhere),
        },
    )
    assert response.json()["error"]["code"] == "OUTPUT_DIR_NOT_ALLOWED"


def test_a_blocking_plan_is_never_queued(app_env: Any, tmp_path: Path, test_media: Path) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)  # video only: no audio to extract
    response = client.post(
        "/api/studio/jobs",
        json={
            "source_path": str(clip),
            "op": "audio",
            "output_name": "x",
            "options": {"codec": "mp3"},
        },
    )
    assert response.json()["error"]["code"] == "SELECTION_INVALID"
    assert client.get("/api/jobs").json() == []


def test_the_file_picker_is_gone(app_env: Any) -> None:
    """The app picks files natively; the server no longer runs an AppleScript picker."""
    response = app_env().post("/api/system/pick-file", json={"prompt": "Dosya seç"})
    assert response.status_code in (404, 405)


def test_the_preview_names_the_file_claim_will_really_use(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    clip = _source(tmp_path, test_media)
    (clip.parent / "clip (kesit).mp4").write_bytes(b"already here")
    plan = (
        app_env()
        .post(
            "/api/studio/plan",
            json={
                "source_path": str(clip),
                "op": "trim",
                "output_name": "clip (kesit)",
                "options": {"mode": "lossless", "segments": [{"start": 0, "end": 1}]},
            },
        )
        .json()
    )
    assert plan["outputs"] == [f"{clip.parent.resolve()}/clip (kesit) (2).mp4"]
    assert "clip (kesit) (2).mp4" in plan["steps"][0]["command"]
    assert all("geçici" not in s["command"] for s in plan["steps"])


def test_malformed_options_are_refused_with_a_code_not_a_500(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    clip = _source(tmp_path, test_media)
    response = app_env().post(
        "/api/studio/plan",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "x",
            "options": {"mode": "lossless", "segments": [{"start": "soon", "end": 1}]},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_OPTION"


def test_separate_segments_become_separate_library_items(
    app_env: Any, tmp_path: Path, test_media: Path
) -> None:
    client = app_env()
    clip = _source(tmp_path, test_media)
    job = client.post(
        "/api/studio/jobs",
        json={
            "source_path": str(clip),
            "op": "trim",
            "output_name": "parts",
            "options": {
                "mode": "lossless",
                "segments": [{"start": 0, "end": 1}, {"start": 2, "end": 3}],
            },
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["status"] == "done")
    items: list[dict[str, Any]] = []
    for _ in range(50):
        items = client.get("/api/library").json()["items"]
        if len(items) == 2:
            break
        time.sleep(0.05)
    assert sorted(i["title"] for i in items) == ["parts.1", "parts.2"]
