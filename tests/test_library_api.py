"""A finished download lands in the library; library actions only ever touch catalogued files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import errors, system
from tests.test_jobs_api import app_env, inspect, wait_for

__all__ = ["app_env"]  # re-exported fixture


def download_audio(client: TestClient) -> dict[str, Any]:
    model = inspect(client)
    job = client.post(
        "/api/jobs",
        json={
            "inspect_id": model["inspect_id"],
            "mode": "audio",
            "audio_format_ids": ["a-tr-m4a"],
            "audio_codec": "m4a",
        },
    ).json()
    return wait_for(client, job["id"], lambda j: j["status"] == "done")


def test_a_finished_download_appears_in_the_library(app_env: Any) -> None:
    client = app_env()
    done = download_audio(client)
    for _ in range(50):  # the catalogue write follows the "done" update
        body = client.get("/api/library").json()
        if body["items"]:
            break
    [item] = body["items"]
    assert item["primary_path"] == done["output_files"][0]
    assert item["kind"] == "audio"
    assert item["title"] == "Local test clip" and item["site"] == "Generic"
    assert item["tracks"]["audio"][0]["codec"] == "aac"
    # The m4a carries the clip's cover art, so the grid gets a real picture.
    thumb = client.get(f"/api/library/{item['id']}/thumbnail")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert body["facets"]["count"] == 1 and body["facets"]["sites"] == ["Generic"]


def test_library_actions_work_by_item_id_only(app_env: Any, tmp_path: Path) -> None:
    client = app_env()
    download_audio(client)
    [item] = client.get("/api/library").json()["items"]
    assert client.post(f"/api/library/{item['id']}/reveal").status_code == 200
    assert client.post(f"/api/library/{item['id']}/open").status_code == 200
    assert client.post("/api/library/not-an-id/open").status_code == 404

    trashed = client.post(f"/api/library/{item['id']}/trash").json()
    assert trashed["status"] == "trashed"
    assert not Path(item["primary_path"]).exists()
    # Fixture mode never touches the real ~/.Trash: files land in the app's simulated trash.
    simulated = tmp_path / "data" / "simulated-trash"
    [moved] = list(simulated.iterdir())
    assert moved.name.endswith(Path(item["primary_path"]).name)
    assert client.get("/api/library").json()["items"] == []
    # A trashed item can no longer be opened.
    assert client.post(f"/api/library/{item['id']}/open").status_code == 409


def test_scan_marks_a_file_deleted_in_finder_as_missing(app_env: Any) -> None:
    client = app_env()
    done = download_audio(client)
    Path(done["output_files"][0]).unlink()
    counts = client.post("/api/library/scan").json()
    assert counts["missing"] == 1
    [item] = client.get("/api/library", params={"status": "missing"}).json()["items"]
    assert item["status"] == "missing"


def test_template_preview_uses_the_samples_the_ui_sends(app_env: Any) -> None:
    body = (
        app_env()
        .post(
            "/api/settings/preview-template",
            json={
                "template": "%(channel)s/%(title)s [%(id)s].%(ext)s",
                "sample": {"channel": "Örnek Kanal", "title": "Örnek başlık", "id": "abc"},
            },
        )
        .json()
    )
    assert body == {"filename": "Örnek Kanal/Örnek başlık [abc].mkv"}


def test_system_actions_never_run_in_fixture_mode(app_env: Any) -> None:
    client = app_env()
    picked = client.post("/api/system/pick-folder", json={"prompt": "Klasör seç"})
    assert picked.status_code == 501
    updated = client.post("/api/system/update-ytdlp")
    assert updated.status_code == 501
    assert updated.json()["error"]["code"] == "UPDATE_UNAVAILABLE"


def test_a_second_update_while_one_runs_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VD_FIXTURE_MODE", raising=False)
    ran: list[list[str]] = []
    monkeypatch.setattr(system.subprocess, "run", lambda argv, **_: ran.append(argv))
    assert system._UPDATING.acquire(blocking=False)
    try:
        with pytest.raises(errors.AppError) as refused:
            system.update_ytdlp()
    finally:
        system._UPDATING.release()
    assert refused.value.code == "UPDATE_RUNNING"
    assert ran == []  # nothing touched the venv


def test_the_updater_upgrades_the_lock_file_not_just_the_venv() -> None:
    lock, sync = system.update_ytdlp_argv()
    assert lock[1:] == ["lock", "--upgrade-package", "yt-dlp", "--upgrade-package", "yt-dlp-ejs"]
    assert sync[1:] == ["sync"]


def test_settings_round_trip_including_the_clipboard_opt_in(app_env: Any) -> None:
    client = app_env()
    settings = client.get("/api/settings").json()
    assert settings["clipboard_watch"] is False  # opt-in, off by default
    saved = client.put("/api/settings", json={**settings, "clipboard_watch": True}).json()
    assert saved["clipboard_watch"] is True
    assert client.get("/api/settings").json()["clipboard_watch"] is True
