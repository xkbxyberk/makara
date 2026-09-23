from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    # Scoped to this module so the opt-in live test is not forced into fixture mode.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("VD_FIXTURE_MODE", "1")
        mp.setenv("VD_DATA_DIR", str(tmp_path_factory.mktemp("data")))
        mp.setenv("VD_DOWNLOAD_DIR", str(tmp_path_factory.mktemp("downloads")))
        from app.main import create_app

        with TestClient(create_app(), base_url="http://127.0.0.1:8787") as test_client:
            yield test_client


def test_health_reports_fixture_mode(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"ok": True, "fixture_mode": True}


def test_doctor_reports_every_dependency(client: TestClient) -> None:
    report = client.get("/api/doctor").json()
    assert {check["id"] for check in report["checks"]} == {"yt_dlp", "js_runtime", "ffmpeg"}
    assert report["status"] in {"ok", "warn", "error"}
    ffmpeg = next(c for c in report["checks"] if c["id"] == "ffmpeg")
    assert "subtitles_filter" in ffmpeg["values"]["capabilities"]


def test_inspect_returns_the_normalised_model(client: TestClient) -> None:
    response = client.post(
        "/api/inspect", json={"url": "https://www.youtube.com/watch?v=0e3GPea1Tyg"}
    )
    assert response.status_code == 200
    model = response.json()
    assert model["kind"] == "video"
    assert len(model["audio_languages"]) == 24
    assert model["commands"]["suggested"].startswith("yt-dlp -f ")
    assert model["source_url"].endswith("0e3GPea1Tyg")


def test_inspect_rejects_a_non_url_with_a_code_not_a_sentence(client: TestClient) -> None:
    response = client.post("/api/inspect", json={"url": "not a url"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"


def test_inspect_reports_an_unsupported_site(client: TestClient) -> None:
    response = client.post("/api/inspect", json={"url": "https://example.com/nothing-here"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_SITE"


def test_command_endpoint_builds_a_multi_audio_selector(client: TestClient) -> None:
    body = client.post(
        "/api/command",
        json={
            "url": "https://www.youtube.com/watch?v=0e3GPea1Tyg",
            "video_format_id": "616",
            "audio_format_ids": ["251-0", "251-1"],
            "subtitle_keys": ["tr", "en"],
        },
    ).json()
    assert "--audio-multistreams" in body["argv"]
    assert "--sub-langs" in body["argv"]


def test_a_rebinding_hostname_is_rejected(client: TestClient) -> None:
    response = client.get("/api/doctor", headers={"host": "evil.example:8787"})
    assert response.status_code == 400


def test_a_cross_site_post_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/inspect",
        json={"url": "https://www.youtube.com/watch?v=0e3GPea1Tyg"},
        headers={"origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_our_own_origin_may_post(client: TestClient) -> None:
    response = client.post(
        "/api/inspect",
        json={"url": "https://www.youtube.com/watch?v=0e3GPea1Tyg"},
        headers={"origin": "http://127.0.0.1:8787"},
    )
    assert response.status_code == 200
