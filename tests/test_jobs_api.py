"""The queue through its HTTP API: inspect -> plan -> job -> real worker -> file on disk."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ffmpeg.probe import probe
from tests.conftest import MEDIA_REQUESTS

LOCAL_URL = "https://example.test/local-media"


@pytest.fixture
def app_env(
    tmp_path: Path, media_server: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[str], TestClient]]:
    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VD_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    clients: list[TestClient] = []

    def make(base: str = media_server) -> TestClient:
        monkeypatch.setenv("VD_FIXTURE_MEDIA_BASE", base)
        from app.main import create_app

        client = TestClient(create_app(), base_url="http://127.0.0.1:8787")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def inspect(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/inspect", json={"url": LOCAL_URL})
    assert response.status_code == 200, response.text
    model: dict[str, Any] = response.json()
    return model


def wait_for(
    client: TestClient,
    job_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    timeout: float = 30,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
        if predicate(job):
            return job
        time.sleep(0.05)
    raise AssertionError(f"timed out; last state: {job}")


def test_defaults_are_original_audio_and_manual_tr_en_subtitles(app_env: Any) -> None:
    model = inspect(app_env())
    mkv = model["defaults"]["mkv"]
    assert mkv["video_format_id"] == "v-vp9"  # the best picture for an archive
    assert mkv["audio_format_ids"] == ["a-en-opus"]  # original only; dubs are opt-in
    assert mkv["subtitle_keys"] == ["tr", "en"]  # manual only; auto captions are opt-in
    compat = model["defaults"]["compat_mp4"]
    assert compat["video_format_id"] == "v-h264"  # plays in QuickTime without re-encoding
    assert compat["audio_format_ids"] == ["a-en-m4a"]


def test_plan_previews_filename_size_and_compatibility(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    plan = client.post(
        "/api/plan",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "compat_mp4",
            "video_format_id": "v-vp9",
            "audio_format_ids": ["a-en-opus"],
        },
    ).json()
    assert (
        plan["filename"] == "Generic/VD Test Channel/2026-09-01 - Local test clip [localclip01].mp4"
    )
    assert plan["size"]["kind"] == "exact" and plan["size"]["bytes"] > 0
    codes = {n["code"] for n in plan["notices"]}
    assert {"VIDEO_REENCODE", "AUDIO_REENCODE", "COMPATIBLE_ALTERNATIVE"} <= codes
    assert plan["plan"]["video"] == "transcode"
    assert "--recode-video" in plan["command"]
    assert plan["blocking"] is False

    bad = client.post(
        "/api/plan",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "mkv",
            "video_format_id": "v-vp9",
            "filename_template": "../../%(title)s.%(ext)s",
        },
    ).json()
    assert bad["filename_error"] == "PATH_OUTSIDE_ROOT" and bad["blocking"] is True


def test_a_job_runs_to_a_verified_mkv(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "mkv",
            "video_format_id": "v-vp9",
            "audio_format_ids": ["a-en-opus", "a-tr-m4a"],
            "subtitle_keys": ["en", "tr"],
        },
    ).json()
    assert job["status"] == "queued"
    done = wait_for(client, job["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done
    [output] = [Path(p) for p in done["output_files"]]
    streams = probe(output)["streams"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert [s["tags"]["language"] for s in audio] == ["eng", "tur"]
    assert len([s for s in streams if s["codec_type"] == "subtitle"]) == 2


def test_an_invalid_selection_is_refused_before_it_is_queued(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    response = client.post("/api/jobs", json={"inspect_id": model["inspect_id"], "mode": "mkv"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SELECTION_INVALID"
    assert client.get("/api/jobs").json() == []


def test_an_expired_inspection_asks_for_a_fresh_one(app_env: Any) -> None:
    response = app_env().post("/api/jobs", json={"inspect_id": "gone", "mode": "mkv"})
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "INSPECT_EXPIRED"


def test_cancel_then_retry_resumes_the_partial_download(app_env: Any, media_server: str) -> None:
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    MEDIA_REQUESTS.clear()
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["stage"] == "downloading" and j["progress"] > 0.2)

    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert cancelled["id"] == job["id"]
    final = wait_for(client, job["id"], lambda j: j["status"] == "cancelled")
    assert final["output_files"] == []

    client.post(f"/api/jobs/{job['id']}/retry")
    done = wait_for(client, job["id"], lambda j: j["status"] == "done")
    assert (
        Path(done["output_files"][0]).stat().st_size
        == (Path(__file__).parent / "fixtures" / "media" / "video_vp9.webm").stat().st_size
    )
    resumed = [
        r for r in MEDIA_REQUESTS if r["path"].endswith("video_vp9.webm") and r["range_start"]
    ]
    assert resumed, f"retry started over instead of resuming: {MEDIA_REQUESTS}"


def test_pause_then_resume_continues_the_partial_download(app_env: Any, media_server: str) -> None:
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    MEDIA_REQUESTS.clear()
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["stage"] == "downloading" and j["progress"] > 0.2)

    client.post(f"/api/jobs/{job['id']}/pause")
    paused = wait_for(client, job["id"], lambda j: j["status"] == "paused")
    assert paused["stage"] == "paused" and paused["output_files"] == []
    assert client.post("/api/jobs/resume-all").json() == {"resumed": 1}
    done = wait_for(client, job["id"], lambda j: j["status"] == "done")
    assert (
        Path(done["output_files"][0]).stat().st_size
        == (Path(__file__).parent / "fixtures" / "media" / "video_vp9.webm").stat().st_size
    )
    resumed = [
        r for r in MEDIA_REQUESTS if r["path"].endswith("video_vp9.webm") and r["range_start"]
    ]
    assert resumed, f"resume started over: {MEDIA_REQUESTS}"


def test_a_download_that_does_not_fit_on_the_disk_is_refused_before_it_starts(
    app_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from app.jobs import planning

    client = app_env()
    model = inspect(client)
    selection = {"inspect_id": model["inspect_id"], "mode": "separate", "video_format_id": "v-vp9"}
    usage = shutil.disk_usage("/")
    monkeypatch.setattr(planning.shutil, "disk_usage", lambda _: usage._replace(free=1024))
    preview = client.post("/api/plan", json=selection).json()
    assert preview["disk"]["enough"] is False and preview["disk"]["free"] == 1024
    response = client.post("/api/jobs", json=selection)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DISK_SPACE_LOW"
    assert client.get("/api/jobs").json() == []


def test_a_network_failure_is_tried_again_later_by_itself(app_env: Any) -> None:
    """P6d: a stream that cannot be reached waits and goes again, keeping what it has; a
    manual "Tekrar dene" starts at once and counts from zero."""
    client = app_env("http://127.0.0.1:9")  # nothing listens there: connection refused
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={"inspect_id": model["inspect_id"], "mode": "separate", "video_format_id": "v-vp9"},
    ).json()
    waiting = wait_for(client, job["id"], lambda j: j["stage"] == "waiting_retry")
    assert waiting["status"] == "queued" and waiting["attempts"] == 1
    assert waiting["error_code"] == "NETWORK"
    assert 20 < waiting["retry_at"] - time.time() <= 30
    # Not picked before its time.
    time.sleep(1.5)
    assert client.get("/api/jobs").json()[0]["stage"] == "waiting_retry"
    client.post(f"/api/jobs/{job['id']}/cancel")
    cancelled = wait_for(client, job["id"], lambda j: j["status"] == "cancelled")
    restarted = client.post(f"/api/jobs/{job['id']}/retry").json()
    assert restarted["attempts"] == 0 and restarted["retry_at"] is None
    assert cancelled["output_files"] == []


def test_remove_deletes_the_entry_but_never_the_media(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "audio",
            "audio_format_ids": ["a-en-m4a"],
            "audio_codec": "m4a",
        },
    ).json()
    done = wait_for(client, job["id"], lambda j: j["status"] == "done")
    output = Path(done["output_files"][0])
    assert client.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
    assert client.get("/api/jobs").json() == []
    assert output.exists()


def test_concurrency_limit_is_respected(app_env: Any, media_server: str) -> None:
    client = app_env(f"{media_server}/slow")
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "concurrency": 1})
    model = inspect(client)
    body = {
        "inspect_id": model["inspect_id"],
        "mode": "separate",
        "video_format_id": "v-vp9",
        "extras": {"thumbnail": False},
    }
    first = client.post("/api/jobs", json=body).json()
    second = client.post("/api/jobs", json=body).json()
    wait_for(client, first["id"], lambda j: j["status"] == "running")
    time.sleep(0.3)
    assert (
        next(j for j in client.get("/api/jobs").json() if j["id"] == second["id"])["status"]
        == "queued"
    )
    for job in (first, second):
        client.post(f"/api/jobs/{job['id']}/cancel")


def test_the_queue_survives_a_restart(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "audio",
            "audio_format_ids": ["a-en-m4a"],
            "audio_codec": "m4a",
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["status"] == "done")
    restarted = app_env()  # same data directory, fresh process state
    assert [j["id"] for j in restarted.get("/api/jobs").json()] == [job["id"]]


def test_settings_reject_a_template_that_escapes_the_root(app_env: Any) -> None:
    client = app_env()
    settings = client.get("/api/settings").json()
    response = client.put("/api/settings", json={**settings, "filename_template": "/etc/%(id)s"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TEMPLATE"


def test_reveal_works_by_job_and_file_index_only(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "audio",
            "audio_format_ids": ["a-en-m4a"],
            "audio_codec": "m4a",
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["status"] == "done")
    assert client.post(f"/api/jobs/{job['id']}/reveal", json={"index": 0}).status_code == 200
    assert client.post(f"/api/jobs/{job['id']}/reveal", json={"index": 5}).status_code == 404
    assert client.post("/api/jobs/nope/reveal", json={"index": 0}).status_code == 404
    # There is no endpoint that reveals an arbitrary path any more.
    assert client.post("/api/reveal", json={"path": "/etc/hosts"}).status_code in (404, 405)


def test_the_disk_root_is_refused_as_a_download_folder(app_env: Any) -> None:
    client = app_env()
    settings = client.get("/api/settings").json()
    for unsafe in ("/", "/System", "/Users"):
        response = client.put("/api/settings", json={**settings, "download_dir": unsafe})
        assert response.json()["error"]["code"] == "DOWNLOAD_DIR_UNSAFE"


def test_events_stream_snapshot_then_live_updates(
    tmp_path: Path, media_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real uvicorn server and a real HTTP stream: TestClient does not model disconnects."""
    import threading

    import httpx
    import uvicorn

    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VD_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setenv("VD_FIXTURE_MEDIA_BASE", media_server)
    from app.main import create_app

    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base, timeout=10) as http:
            model = http.post("/api/inspect", json={"url": LOCAL_URL}).json()
            events: list[str] = []
            with http.stream("GET", "/api/events") as stream:
                lines = stream.iter_lines()
                for line in lines:
                    if line.startswith("event:"):
                        events.append(line)
                    if line == "event: snapshot":
                        break
                http.post(
                    "/api/jobs",
                    json={
                        "inspect_id": model["inspect_id"],
                        "mode": "audio",
                        "audio_format_ids": ["a-en-m4a"],
                        "audio_codec": "m4a",
                    },
                )
                statuses = []
                for line in lines:
                    if line.startswith("data:") and '"type": "job"' in line:
                        statuses.append(line)
                        if '"status": "done"' in line:
                            break
        assert events[0] == "event: snapshot"
        assert any('"stage": "downloading"' in s for s in statuses)
        assert '"status": "done"' in statuses[-1]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive(), "server did not shut down with an event stream attached"


def test_a_retry_within_the_kill_grace_period_is_not_killed(
    app_env: Any, media_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delayed SIGKILL of a cancel must hit the cancelled process, never its retry."""
    from app.jobs import manager as manager_module

    monkeypatch.setattr(manager_module, "CANCEL_GRACE_SECONDS", 0.4)
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["stage"] == "downloading")
    client.post(f"/api/jobs/{job['id']}/cancel")
    wait_for(client, job["id"], lambda j: j["status"] == "cancelled")
    client.post(f"/api/jobs/{job['id']}/retry")
    done = wait_for(client, job["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done["error_raw"]


def test_parallel_submissions_never_exceed_the_concurrency_limit(
    app_env: Any, media_server: str
) -> None:
    import threading

    client = app_env(f"{media_server}/slow")
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "concurrency": 1})
    model = inspect(client)
    body = {
        "inspect_id": model["inspect_id"],
        "mode": "separate",
        "video_format_id": "v-vp9",
        "extras": {"thumbnail": False},
    }
    threads = [
        threading.Thread(target=lambda: client.post("/api/jobs", json=body)) for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    peak = 0
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()
        peak = max(peak, sum(1 for j in jobs if j["status"] == "running"))
        time.sleep(0.02)
    assert len(client.get("/api/jobs").json()) == 6
    assert peak == 1
    for job in client.get("/api/jobs").json():
        client.post(f"/api/jobs/{job['id']}/cancel")


def test_a_cancel_right_after_submitting_is_never_lost(app_env: Any, media_server: str) -> None:
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    client.post(f"/api/jobs/{job['id']}/cancel")
    final = wait_for(client, job["id"], lambda j: j["status"] in ("cancelled", "done", "failed"))
    assert final["status"] == "cancelled"
    assert final["output_files"] == []


def test_a_job_interrupted_by_a_restart_is_requeued_and_resumed(
    app_env: Any, media_server: str
) -> None:
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    MEDIA_REQUESTS.clear()
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["stage"] == "downloading" and j["progress"] > 0.2)
    client.__exit__(None, None, None)  # the server stops mid-download
    restarted = app_env(f"{media_server}/slow")
    done = wait_for(restarted, job["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done["error_raw"]
    assert any(r["range_start"] for r in MEDIA_REQUESTS if r["path"].endswith("video_vp9.webm"))


def test_identical_downloads_keep_their_own_files_when_one_is_deleted(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    body = {
        "inspect_id": model["inspect_id"],
        "mode": "audio",
        "audio_format_ids": ["a-en-m4a"],
        "audio_codec": "m4a",
    }
    first = wait_for(
        client, client.post("/api/jobs", json=body).json()["id"], lambda j: j["status"] == "done"
    )
    wait_for(
        client, client.post("/api/jobs", json=body).json()["id"], lambda j: j["status"] == "done"
    )
    deleted = first["output_files"][0]
    Path(deleted).unlink()
    client.post("/api/library/scan")
    items = client.get("/api/library").json()["items"]
    primaries = [i["primary_path"] for i in items]
    assert len(set(primaries)) == 2, "two records now point at the same file"
    assert any(i["status"] == "missing" for i in items)


@pytest.mark.parametrize(
    ("folder", "code"),
    [
        ("~", "DOWNLOAD_DIR_UNSAFE"),
        ("~/Library/Mail", "DOWNLOAD_DIR_UNSAFE"),
        ("/System/Library", "DOWNLOAD_DIR_UNSAFE"),
        ("/usr/local/share", "DOWNLOAD_DIR_UNSAFE"),
        ("relative/path", "DOWNLOAD_DIR_NOT_ABSOLUTE"),
        ("/nonexistent-parent/child", "DOWNLOAD_DIR_MISSING"),
    ],
)
def test_unsafe_or_unusable_download_folders_are_refused(
    app_env: Any, folder: str, code: str
) -> None:
    client = app_env()
    settings = client.get("/api/settings").json()
    response = client.put("/api/settings", json={**settings, "download_dir": folder})
    assert response.json()["error"]["code"] == code


def test_a_file_is_not_a_download_folder(app_env: Any, tmp_path: Path) -> None:
    client = app_env()
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    settings = client.get("/api/settings").json()
    response = client.put("/api/settings", json={**settings, "download_dir": str(a_file)})
    assert response.json()["error"]["code"] == "DOWNLOAD_DIR_NOT_A_FOLDER"


def test_updating_yt_dlp_is_refused_while_a_job_runs(app_env: Any, media_server: str) -> None:
    client = app_env(f"{media_server}/slow")
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "separate",
            "video_format_id": "v-vp9",
            "extras": {"thumbnail": False},
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["status"] == "running")
    response = client.post("/api/system/update-ytdlp")
    assert response.status_code == 409 and response.json()["error"]["code"] == "JOBS_RUNNING"
    client.post(f"/api/jobs/{job['id']}/cancel")


def test_a_cancel_while_files_are_being_placed_is_ignored(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "audio",
            "audio_format_ids": ["a-en-m4a"],
            "audio_codec": "m4a",
        },
    ).json()
    wait_for(client, job["id"], lambda j: j["status"] == "done")
    store = client.app.state.jobs.store  # type: ignore[attr-defined]
    store.update(job["id"], status="running", stage="finalizing")
    after = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert after["stage"] == "finalizing"
    assert job["id"] not in client.app.state.jobs.cancelling  # type: ignore[attr-defined]


def test_a_quick_choice_downloads_exactly_what_its_row_promised(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    rows = {r["id"]: r for r in model["offers"]["video"]}
    assert set(rows) == {"v360-25-sdr", "v240-25-sdr"}
    response = client.post(
        "/api/quick",
        json={"inspect_id": model["inspect_id"], "offer_id": "v240-25-sdr", "output": "compat_mp4"},
    )
    assert response.status_code == 200, response.text
    quick = response.json()
    assert (
        quick["selection"]["video_format_id"]
        == rows["v240-25-sdr"]["outputs"]["compat_mp4"]["video_format_id"]
    )
    # The caller remembers this for the next video.
    assert quick["rule"] == {
        "kind": "video",
        "height": 240,
        "fps": 25,
        "hdr": False,
        "output": "compat_mp4",
    }
    done = wait_for(client, quick["job"]["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done
    [output] = [Path(p) for p in done["output_files"]]
    assert output.suffix == ".mp4"
    streams = probe(output)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    assert (video["codec_name"], video["height"]) == ("h264", 240)
    # Original audio and the manual TR/EN subtitles, as everywhere else.
    assert [s["tags"]["language"] for s in streams if s["codec_type"] == "audio"] == ["eng"]
    assert len([s for s in streams if s["codec_type"] == "subtitle"]) == 2


def test_a_url_and_a_remembered_rule_are_enough_for_one_click(app_env: Any) -> None:
    client = app_env()
    response = client.post(
        "/api/quick", json={"url": LOCAL_URL, "rule": {"kind": "audio", "format": "m4a"}}
    )
    assert response.status_code == 200, response.text
    quick = response.json()
    assert quick["offer_id"] == "a-m4a" and quick["output"] is None
    assert quick["selection"]["mode"] == "audio" and quick["selection"]["audio_codec"] == "m4a"
    done = wait_for(client, quick["job"]["id"], lambda j: j["status"] in ("done", "failed"))
    assert done["status"] == "done", done
    [output] = [Path(p) for p in done["output_files"]]
    assert output.suffix == ".m4a"
    [audio] = [s for s in probe(output)["streams"] if s["codec_type"] == "audio"]
    assert audio["codec_name"] == "aac"  # copied, as the row said: no re-encode


def test_quick_refuses_what_it_cannot_do(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    unknown = client.post(
        "/api/quick", json={"inspect_id": model["inspect_id"], "offer_id": "v4320-60-hdr"}
    )
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (400, "OFFER_UNKNOWN")
    nothing = client.post("/api/quick", json={})
    assert nothing.json()["error"]["code"] == "QUICK_NEEDS_SOURCE"
    playlist = client.post("/api/quick", json={"url": "https://www.youtube.com/playlist?list=PL1"})
    assert playlist.json()["error"]["code"] == "QUICK_NEEDS_VIDEO"
    expired = client.post("/api/quick", json={"inspect_id": "gone", "offer_id": "v240-25-sdr"})
    assert (expired.status_code, expired.json()["error"]["code"]) == (410, "INSPECT_EXPIRED")
    assert client.get("/api/jobs").json() == []  # nothing was queued by any of these


def test_quick_refuses_a_language_the_video_does_not_have(app_env: Any) -> None:
    client = app_env()
    model = inspect(client)
    response = client.post(
        "/api/quick",
        json={"inspect_id": model["inspect_id"], "offer_id": "v240-25-sdr", "audio_language": "ja"},
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        400,
        "AUDIO_LANGUAGE_UNKNOWN",
    )
    german = client.post(
        "/api/quick",
        json={"inspect_id": model["inspect_id"], "offer_id": "v240-25-sdr", "audio_language": "de"},
    ).json()
    assert german["selection"]["audio_format_ids"] == ["a-de-m4a"]
    assert [j["id"] for j in client.get("/api/jobs").json()] == [german["job"]["id"]]


def test_quick_without_an_output_follows_the_default_mode(app_env: Any) -> None:
    client = app_env()
    settings = client.get("/api/settings").json()
    saved = client.put("/api/settings", json={**settings, "default_mode": "compat_mp4"})
    assert saved.status_code == 200, saved.text
    model = inspect(client)
    quick = client.post(
        "/api/quick", json={"inspect_id": model["inspect_id"], "offer_id": "v360-25-sdr"}
    ).json()
    assert quick["selection"]["mode"] == "compat_mp4" and quick["output"] == "compat_mp4"


def test_quick_reports_extraction_failures_like_inspect(app_env: Any) -> None:
    client = app_env()
    url = "https://unknown.example.com/watch"
    inspected = client.post("/api/inspect", json={"url": url})
    quick = client.post("/api/quick", json={"url": url, "rule": {"kind": "video"}})
    assert quick.status_code == inspected.status_code
    assert quick.json()["error"]["code"] == inspected.json()["error"]["code"]
