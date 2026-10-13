from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

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
    assert {check["id"] for check in report["checks"]} == {
        "yt_dlp",
        "js_runtime",
        "ffmpeg",
        "safari_session",
    }
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


def test_the_web_pages_own_endpoints_are_gone(client: TestClient) -> None:
    """The browser UI was removed (N8): nothing may still open a picker or post a notification
    for whoever asks. (Commands are built by /api/plan; test_errors_and_command covers them.)"""
    for path in ["/api/command", "/api/notify", "/api/system/pick-folder", "/api/system/pick-file"]:
        assert client.post(path, json={"prompt": "x", "title": "x", "url": "x"}).status_code in (
            404,
            405,
        ), path


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


def test_ffmpeg_full_is_preferred_when_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Homebrew's keg-only ffmpeg-full is never on PATH; the app must still find and prefer it."""
    from app.ffmpeg import binaries

    monkeypatch.setattr(binaries, "FULL_KEG", tmp_path / "missing")
    plain = binaries.find("ffmpeg")
    assert not binaries.is_full(plain)

    keg = tmp_path / "keg"
    keg.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        (keg / name).write_text("#!/bin/sh\n")
        (keg / name).chmod(0o755)
    monkeypatch.setattr(binaries, "FULL_KEG", keg)
    assert binaries.find("ffmpeg") == str(keg / "ffmpeg")
    assert binaries.find("ffprobe") == str(keg / "ffprobe")
    assert binaries.is_full(binaries.ffmpeg())

    (keg / "ffprobe").unlink()  # half an install: never mix binaries from two builds
    assert binaries.find("ffmpeg") == plain


def test_doctor_points_at_ffmpeg_full_when_the_plain_build_lacks_libass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import doctor
    from app.ffmpeg import binaries

    monkeypatch.setattr(binaries, "FULL_KEG", tmp_path / "not-installed")
    check = doctor._ffmpeg_check()
    if check["values"]["missing_optional"]:
        assert check["status"] == "warn"
        assert check["fix"] == {"kind": "command", "command": "brew install ffmpeg-full"}
    else:  # a plain build that already has everything needs no advice
        assert check["fix"]["kind"] == "none"


def test_inspect_lists_the_videos_own_quick_choices_and_preselects_one(
    client: TestClient,
) -> None:
    url = "https://www.youtube.com/watch?v=0e3GPea1Tyg"
    model = client.post("/api/inspect", json={"url": url}).json()
    offers = model["offers"]
    assert offers["video"][0]["id"] == "v1080-24-sdr"
    assert {r["format"] for r in offers["audio"]} == {"m4a", "opus", "mp3"}
    assert offers["preselected"] == {"offer_id": "v1080-24-sdr", "output": "mkv"}

    rule = {"kind": "video", "height": 720, "output": "compat_mp4"}
    model = client.post("/api/inspect", json={"url": url, "rule": rule}).json()
    assert model["offers"]["preselected"] == {"offer_id": "v720-24-sdr", "output": "compat_mp4"}


def test_a_reused_inspection_is_the_same_one_and_a_fresh_one_is_not(client: TestClient) -> None:
    url = "https://www.youtube.com/watch?v=iG9CE55wbtY"
    first = client.post("/api/inspect", json={"url": url}).json()
    again = client.post("/api/inspect", json={"url": url, "reuse": True}).json()
    fresh = client.post("/api/inspect", json={"url": url}).json()
    assert again["inspect_id"] == first["inspect_id"]
    assert fresh["inspect_id"] != first["inspect_id"]
    # Preselection is computed per request; the cached model itself is never changed.
    rule = {"kind": "audio", "format": "opus"}
    with_rule = client.post("/api/inspect", json={"url": url, "reuse": True, "rule": rule}).json()
    assert with_rule["offers"]["preselected"]["offer_id"] == "a-opus"
    plain = client.post("/api/inspect", json={"url": url, "reuse": True}).json()
    assert plain["offers"]["preselected"]["offer_id"] != "a-opus"


def test_a_bad_rule_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/inspect",
        json={"url": "https://www.youtube.com/watch?v=0e3GPea1Tyg", "rule": {"kind": "both"}},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("url", "supported", "extractor"),
    [
        ("https://www.youtube.com/watch?v=xnP7qKxwzjg", True, "Youtube"),
        ("https://www.youtube.com/@MrBeast", True, "YoutubeTab"),
        ("https://vimeo.com/76979871", True, "Vimeo"),
        # The generic extractor matches anything, so it does not count.
        ("https://www.apple.com/", False, None),
        ("https://www.netflix.com/watch/80100172", False, None),
        ("file:///etc/passwd", False, None),
        ("javascript:alert(1)", False, None),
        # In fixture mode the recorded test URLs count, so the e2e suite can use them.
        ("https://example.test/local-media", True, "fixture"),
    ],
)
def test_supports_answers_offline_from_extractor_patterns(
    client: TestClient, url: str, supported: bool, extractor: str | None
) -> None:
    response = client.get("/api/supports", params={"url": url}).json()
    assert response["supported"] is supported
    assert response["extractor"] == extractor


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://www.youtube.com/watch?v=xnP7qKxwzjg", "video"),
        ("https://vimeo.com/76979871", "video"),
        # A channel or user page cannot be one click: the extension opens it in the app.
        ("https://soundcloud.com/someartist", "playlist"),
        # yt-dlp cannot say from the URL alone (a channel tab may be a list or a live video).
        ("https://www.youtube.com/@MrBeast", "unknown"),
        ("HTTPS://WWW.YOUTUBE.COM/watch?v=xnP7qKxwzjg", "video"),
    ],
)
def test_supports_says_whether_a_page_is_one_video_or_a_list(
    client: TestClient, url: str, kind: str
) -> None:
    response = client.get("/api/supports", params={"url": url}).json()
    assert response["supported"] is True
    assert response["kind"] == kind


def test_the_extension_is_served_only_inside_its_folder_and_only_in_fixture_mode(
    client: TestClient,
) -> None:
    assert client.get("/__test/extension/popup.html").status_code == 200
    assert client.get("/__test/extension/_locales/tr/messages.json").status_code == 200
    # Whatever the client or the router makes of these, no file outside the folder comes back.
    for escape in [
        "../../backend/app/main.py",
        "..%2F..%2Fbackend%2Fapp%2Fmain.py",
        "%2Fetc%2Fpasswd",
    ]:
        body = client.get(f"/__test/extension/{escape}").text
        assert "create_app" not in body and "root:" not in body, escape


def test_outside_fixture_mode_there_is_no_extension_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VD_FIXTURE_MODE", raising=False)
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VD_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    from app.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1:8787") as plain:
        response = plain.get("/__test/extension/popup.html")
        assert response.status_code == 404


def test_api_answers_are_never_cached(client: TestClient) -> None:
    for path in ["/api/health", "/api/supports?url=https://www.youtube.com/watch?v=x", "/api/jobs"]:
        assert client.get(path).headers["cache-control"] == "no-store", path


def test_the_extension_reads_how_to_offer_a_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    from app.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1:8787") as own:
        # Berk's choice: the card on the page by default; "icon" keeps to the toolbar.
        assert own.get("/api/extension").json() == {"offer": "page"}
        settings = own.get("/api/settings").json()
        assert (
            own.put("/api/settings", json={**settings, "extension_offer": "icon"}).status_code
            == 200
        )
        assert own.get("/api/extension").json() == {"offer": "icon"}
        refused = own.put("/api/settings", json={**settings, "extension_offer": "always"})
        assert refused.status_code == 422


def test_the_safari_session_setting_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    from app.main import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1:8787") as own:
        settings = own.get("/api/settings").json()
        assert settings["safari_login"] is True  # Berk's choice: on by default
        saved = own.put("/api/settings", json={**settings, "safari_login": False}).json()
        assert saved["safari_login"] is False
        assert own.get("/api/settings").json()["safari_login"] is False


def test_there_is_no_web_page_only_the_api(client: TestClient) -> None:
    """The app is native since N7 and the browser UI is gone (N8): no path serves a page, and an
    unknown API path is a 404 too."""
    for path in ["/", "/library", "/index.html", "/assets/index.js", "/api/no-such-thing"]:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "NOT_FOUND", path
