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
