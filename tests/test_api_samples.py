"""Contract samples for the native app.

Real responses from the fixture-mode server, scrubbed of ids, times and paths, are kept in
`tests/fixtures/api/`. The Swift tests (macos/VideoDownloaderKit) decode every one of them, so a
change to the API shape fails here first -- or there, if the samples were regenerated:

    VD_WRITE_API_SAMPLES=1 uv run pytest -q tests/test_api_samples.py
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

SAMPLES = Path(__file__).parent / "fixtures" / "api"
LOCAL_URL = "https://example.test/local-media"
MULTI_AUDIO_URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"
PLAYLIST_URL = "https://www.youtube.com/@TED/videos"
VOLATILE_KEYS = {
    "id",
    "inspect_id",
    "job_id",
    "created_at",
    "started_at",
    "finished_at",
    "updated_at",
    "added_at",
    "checked_at",
    "free",  # this Mac's free disk space (the plan's disk check)
}


def scrub(value: Any, key: str = "") -> Any:
    """Keep the shape and the meaningful values; replace what differs on every run."""
    if isinstance(value, dict):
        return {k: scrub(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, key) for v in value]
    if key in VOLATILE_KEYS and value is not None:
        return 0 if isinstance(value, (int, float)) else "<id>"
    if isinstance(value, str) and value.startswith(("/", "http://127.0.0.1")):
        return "<path>"
    if key in ("speed", "eta", "progress") and isinstance(value, (int, float)):
        return 0
    return value


def scrub_doctor(report: dict[str, Any]) -> dict[str, Any]:
    """Versions, paths and this build's capabilities change with every update: keep the ids, the
    keys and the value types (what the app decodes), and the Safari session state (fixed in
    tests). Statuses stay real; one runtime stands for however many this Mac has."""

    def leaf(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: leaf(v) for k, v in value.items()}
        if isinstance(value, list):
            return [leaf(v) for v in value]
        if isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            return 0
        return value if value is None else "<value>"

    checks = []
    for check in report["checks"]:
        values = {k: v if k == "state" else leaf(v) for k, v in check["values"].items()}
        if "found" in values:
            values["found"] = values["found"][:1]
        checks.append({**check, "values": values})
    return {"status": report["status"], "checks": checks}


def check(name: str, data: Any, scrubbed_already: bool = False) -> None:
    path = SAMPLES / f"{name}.json"
    scrubbed = data if scrubbed_already else scrub(data)
    if os.environ.get("VD_WRITE_API_SAMPLES") == "1":
        SAMPLES.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(scrubbed, indent=2, ensure_ascii=False) + "\n", "utf-8")
        return
    assert path.exists(), f"missing sample {path.name}; regenerate with VD_WRITE_API_SAMPLES=1"
    assert json.loads(path.read_text("utf-8")) == scrubbed, (
        f"the API shape of {name} changed: update the Swift models, then regenerate the samples"
    )


@pytest.fixture
def client(
    tmp_path: Path, media_server: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VD_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setenv("VD_FIXTURE_MEDIA_BASE", media_server)
    from app.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1:8787") as test_client:
        yield test_client


def test_samples_for_the_native_app(client: TestClient) -> None:
    check("health", client.get("/api/health").json())
    check("settings", client.get("/api/settings").json())
    check("error", client.post("/api/quick", json={}).json())
    check("supports", client.get("/api/supports", params={"url": LOCAL_URL}).json())
    check("doctor", scrub_doctor(client.get("/api/doctor").json()), scrubbed_already=True)

    # What the native İncele screen reads: a video (with offers), a playlist, and a plan.
    multi = client.post("/api/inspect", json={"url": MULTI_AUDIO_URL, "rule": None}).json()
    # Offer, thumbnail and entry ids are content, not volatile: only the inspect id changes.
    check("inspect-video", {**multi, "inspect_id": "<id>"}, scrubbed_already=True)
    playlist = client.post("/api/inspect", json={"url": PLAYLIST_URL}).json()
    check("inspect-playlist", playlist, scrubbed_already=True)
    selection = {
        "inspect_id": multi["inspect_id"],
        # The archive's AV1 + Opus in an MP4: notices that carry params (codec, height).
        "mode": "compat_mp4",
        **multi["defaults"]["mkv"],
        "audio_codec": None,
        "audio_quality": None,
        "filename_template": None,
        "extras": {
            "thumbnail": True,
            "thumbnail_file": False,
            "description": False,
            "info_json": False,
        },
    }
    check("plan", client.post("/api/plan", json=selection).json())

    quick = client.post("/api/quick", json={"url": LOCAL_URL, "rule": {"kind": "video"}}).json()
    job_id = quick["job"]["id"]
    deadline = time.monotonic() + 30
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    check("jobs", client.get("/api/jobs").json())
    # What an SSE `job` event carries, as the manager publishes it.
    check("event-job", {"type": "job", "job": job})

    # The finished download, as Kütüphane lists it (catalogued just after the job ends).
    library: dict[str, Any] = {}
    while time.monotonic() < deadline:
        library = client.get("/api/library").json()
        if library["items"]:
            break
        time.sleep(0.05)
    assert library["items"], "the download was never catalogued"
    check("library", library)
    check("scan", client.post("/api/library/scan").json())
