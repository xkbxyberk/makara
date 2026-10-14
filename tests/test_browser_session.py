"""Videos that need a signed-in account use Berk's Safari session -- only those, only on retry."""

from __future__ import annotations

import asyncio
import json
import os
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any

import pytest

from app import browser_session, doctor, errors, inspect_service
from app import settings as settings_store
from app.jobs import planning
from app.workers import inspect_worker

FIXTURE = Path(__file__).parent / "fixtures" / "infojson" / "youtube_multi_audio.json"
URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real-mode server (no fixtures) whose Safari session is a file of the test's own."""
    monkeypatch.delenv("VD_FIXTURE_MODE", raising=False)
    path = tmp_path / "Cookies.binarycookies"
    path.write_bytes(b"cook")
    monkeypatch.setenv("VD_SAFARI_COOKIES", str(path))
    return path


def fake_worker(monkeypatch: pytest.MonkeyPatch, answers: list[Any]) -> list[Any]:
    calls: list[Any] = []

    async def run(url: str, cookies: list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
        calls.append(cookies)
        answer = answers[len(calls) - 1]
        if isinstance(answer, errors.AppError):
            raise answer
        return answer, []

    monkeypatch.setattr(inspect_service, "_run_worker", run)
    return calls


def info() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def test_an_age_restricted_video_is_retried_once_with_the_session(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_worker(monkeypatch, [errors.AppError(code="AGE_RESTRICTED"), info()])
    model = asyncio.run(inspect_service.inspect(URL))
    assert calls == [None, ["safari", str(session), "youtube"]]
    assert "USED_SAFARI_LOGIN" in model["warnings"]
    # Its download needs the session too: it extracts again (CLAUDE.md gotcha 20).
    entry = inspect_service.recall(model["inspect_id"])
    selection = {"mode": "mkv", **model["defaults"]["mkv"]}
    job = planning.build_job(entry, selection, settings_store.Settings())
    assert job["request"]["cookies_from_browser"] == ["safari", str(session), "youtube"]


def test_an_ordinary_video_never_carries_the_session(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_worker(monkeypatch, [info()])
    model = asyncio.run(inspect_service.inspect(URL))
    assert calls == [None]
    assert "USED_SAFARI_LOGIN" not in model["warnings"]
    entry = inspect_service.recall(model["inspect_id"])
    job = planning.build_job(
        entry, {"mode": "mkv", **model["defaults"]["mkv"]}, settings_store.Settings()
    )
    assert job["request"]["cookies_from_browser"] is None


@pytest.mark.parametrize("code", ["GEO_RESTRICTED", "VIDEO_UNAVAILABLE", "NETWORK", "BOT_CHECK"])
def test_other_failures_are_not_retried_with_an_account(
    session: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    calls = fake_worker(monkeypatch, [errors.AppError(code=code)])
    with pytest.raises(errors.AppError) as caught:
        asyncio.run(inspect_service.inspect(URL))
    assert caught.value.code == code
    assert calls == [None]


def test_the_setting_turns_the_retry_off(session: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_store.save(settings_store.Settings(safari_login=False))
    calls = fake_worker(monkeypatch, [errors.AppError(code="LOGIN_REQUIRED")])
    with pytest.raises(errors.AppError) as caught:
        asyncio.run(inspect_service.inspect(URL))
    assert caught.value.code == "LOGIN_REQUIRED"
    assert calls == [None]


def test_still_refused_with_the_session_says_why(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_worker(
        monkeypatch,
        [errors.AppError(code="AGE_RESTRICTED"), errors.AppError(code="AGE_RESTRICTED")],
    )
    with pytest.raises(errors.AppError) as caught:
        asyncio.run(inspect_service.inspect(URL))
    assert caught.value.code == "SESSION_NOT_ENOUGH"
    assert caught.value.detail == {"first": "AGE_RESTRICTED"}


def test_fixture_mode_has_no_session_unless_a_test_gives_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VD_FIXTURE_MODE", "1")
    monkeypatch.delenv("VD_SAFARI_COOKIES", raising=False)
    assert browser_session.cookies_path() is None
    assert browser_session.ytdlp_option() is None


def test_tests_never_point_at_berks_real_safari() -> None:
    path = browser_session.cookies_path()
    assert path is not None and path != browser_session.SAFARI_COOKIES
    assert not str(path).startswith(str(Path.home() / "Library"))


def test_status_says_what_is_missing(session: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session.unlink()
    assert browser_session.status() == {
        "available": False,
        "readable": False,
        "youtube_signed_in": None,
    }
    session.write_bytes(b"cook")
    os.chmod(session, 0)
    try:
        assert browser_session.status()["readable"] is False  # as without Full Disk Access
        check = doctor._safari_session_check()
        assert (
            check["values"] == {"state": "no_access"} and check["fix"]["kind"] == "full_disk_access"
        )
    finally:
        os.chmod(session, 0o644)
    # A file yt-dlp cannot parse: say nothing rather than guess.
    assert browser_session.status() == {
        "available": True,
        "readable": True,
        "youtube_signed_in": None,
    }


def cookie(name: str, domain: str) -> Cookie:
    return Cookie(
        0,
        name,
        "secret",
        None,
        False,
        domain,
        True,
        True,
        "/",
        True,
        True,
        None,
        False,
        None,
        None,
        {},
    )


@pytest.mark.parametrize(
    ("cookies", "state"),
    [
        ([cookie("SAPISID", ".youtube.com")], "signed_in"),
        ([cookie("PREF", ".youtube.com"), cookie("SAPISID", ".google.com")], "signed_out"),
    ],
)
def test_signed_in_is_told_by_cookie_names_only(
    session: Path, monkeypatch: pytest.MonkeyPatch, cookies: list[Cookie], state: str
) -> None:
    import yt_dlp.cookies

    monkeypatch.setattr(yt_dlp.cookies, "parse_safari_cookies", lambda data: cookies)
    expected: dict[str, Any] = {"state": state}
    if state == "signed_in":
        expected["sites"] = ["YouTube"]  # which session sites are signed in, nothing more
    assert doctor._safari_session_check()["values"] == expected


def test_the_doctor_says_off_when_the_setting_is_off(session: Path) -> None:
    settings_store.save(settings_store.Settings(safari_login=False))
    assert doctor._safari_session_check() == {
        "id": "safari_session",
        "status": "ok",
        "values": {"state": "off"},
        "fix": {"kind": "none", "command": ""},
    }


def test_an_unreadable_session_is_its_own_error_in_the_worker(tmp_path: Path) -> None:
    # Not named *.binarycookies: the code must come from the worker, not from a message pattern.
    locked = tmp_path / "plain.db"
    locked.write_bytes(b"cook")
    os.chmod(locked, 0)
    try:
        result = inspect_worker.run({"url": URL, "cookies_from_browser": ["safari", str(locked)]})
    finally:
        os.chmod(locked, 0o644)
    assert result["ok"] is False
    assert result["error"]["code"] == "COOKIES_UNREADABLE"


def test_macos_refusing_the_file_is_classified_too() -> None:
    message = (
        "[Errno 1] Operation not permitted: '/Users/x/Library/Containers/com.apple.Safari"
        "/Data/Library/Cookies/Cookies.binarycookies'"
    )
    assert errors.classify(message) == "COOKIES_UNREADABLE"


def test_only_the_session_sites_are_ever_retried_with_the_session(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """YouTube (2026-10-13), Reddit, Instagram and X (Berk, 2026-10-14): each with its own
    cookies only. Any other site, or a look-alike host, never gets the session."""
    for url in [
        "https://vimeo.com/1",
        "https://bank.example/login",
        "https://instagram.com.evil.example/p/x/",
        "https://notreddit.com/r/x/comments/1/",
    ]:
        calls = fake_worker(monkeypatch, [errors.AppError(code="LOGIN_REQUIRED")])
        with pytest.raises(errors.AppError):
            asyncio.run(inspect_service.inspect(url))
        assert calls == [None], url
    for url in [
        "https://youtu.be/x",
        "https://music.youtube.com/watch?v=x",
        "https://m.youtube.com/watch?v=x",
    ]:
        assert browser_session.is_youtube_url(url), url
    assert not browser_session.is_youtube_url("https://notyoutube.com/watch?v=x")
    assert not browser_session.is_youtube_url("https://youtube.com.evil.example/")
    for url, site in [
        ("https://www.reddit.com/r/videos/comments/abc/x/", "reddit"),
        ("https://v.redd.it/abc", "reddit"),
        ("https://www.instagram.com/reel/C9x/", "instagram"),
        ("https://x.com/nasa/status/1", "x"),
        ("https://mobile.twitter.com/nasa/status/1", "x"),
    ]:
        assert browser_session.site_of(url) == site, url
        first: list[Any] = [] if site == "reddit" else [errors.AppError(code="LOGIN_REQUIRED")]
        calls = fake_worker(monkeypatch, [*first, info()])
        asyncio.run(inspect_service.inspect(url))
        if site == "reddit":  # no anonymous answers there any more: the session goes first
            assert calls == [["safari", str(session), site]], url
        else:
            assert calls[0] is None and calls[1] == ["safari", str(session), site], url


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("Unsupported URL: https://www.mybank.com/login?next=/", "UNSUPPORTED_SITE"),
        ("Unable to download webpage: https://login.example.com/ (caused by timed out)", "NETWORK"),
        ("Sign in to confirm your age. Use --cookies-from-browser", "AGE_RESTRICTED"),
        ("Sign in to confirm you're not a bot", "BOT_CHECK"),
    ],
)
def test_an_address_in_a_message_never_decides_its_code(message: str, code: str) -> None:
    assert errors.classify(message) == code


def test_turning_the_setting_off_stops_the_session_everywhere(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_worker(monkeypatch, [errors.AppError(code="AGE_RESTRICTED"), info(), info()])
    model = asyncio.run(inspect_service.inspect(URL))
    entry = inspect_service.recall(model["inspect_id"])
    off = settings_store.Settings(safari_login=False)
    settings_store.save(off)
    job = planning.build_job(entry, {"mode": "mkv", **model["defaults"]["mkv"]}, off)
    assert job["request"]["cookies_from_browser"] is None
    # The cached inspection made with the session is not reused once it is off.
    again = asyncio.run(inspect_service.inspect(URL, reuse=True))
    assert again["inspect_id"] != model["inspect_id"]
    assert calls[-1] is None


class FakeYDL:
    def __init__(self) -> None:
        self.cookiejar = __import__("http.cookiejar").cookiejar.CookieJar()


def test_a_worker_gets_the_youtube_cookies_and_no_other_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import session

    store = tmp_path / "store.db"
    store.write_bytes(b"x")
    jar = [
        cookie("SAPISID", ".youtube.com"),
        cookie("SID", ".google.com"),
        cookie("auth", "bank.example"),
        cookie("PREF", "www.youtube.com"),
    ]
    monkeypatch.setattr("yt_dlp.cookies.parse_safari_cookies", lambda data: jar)
    ydl = FakeYDL()
    assert session.apply(ydl, ["safari", str(store)]) == 2
    assert sorted(c.domain for c in ydl.cookiejar) == [".youtube.com", "www.youtube.com"]
    assert session.apply(FakeYDL(), None) == 0
    with pytest.raises(errors.AppError) as caught:
        session.apply(FakeYDL(), ["safari", str(tmp_path / "missing.db")])
    assert caught.value.code == "COOKIES_UNREADABLE"
    with pytest.raises(errors.AppError):
        session.apply(FakeYDL(), ["chrome", str(store)])


def test_each_site_gets_its_own_cookies_and_no_other_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import session

    store = tmp_path / "store.db"
    store.write_bytes(b"x")
    jar = [
        cookie("SAPISID", ".youtube.com"),
        cookie("reddit_session", ".reddit.com"),
        cookie("sessionid", ".instagram.com"),
        cookie("auth_token", ".x.com"),
        cookie("auth_token", ".twitter.com"),
        cookie("auth", "notreddit.com"),
        cookie("auth", "x.com.evil.example"),
    ]
    monkeypatch.setattr("yt_dlp.cookies.parse_safari_cookies", lambda data: jar)
    for site, domains in [
        ("reddit", [".reddit.com"]),
        ("instagram", [".instagram.com"]),
        ("x", [".twitter.com", ".x.com"]),
        ("youtube", [".youtube.com"]),
    ]:
        ydl = FakeYDL()
        session.apply(ydl, ["safari", str(store), site])
        assert sorted(c.domain for c in ydl.cookiejar) == domains, site
    with pytest.raises(errors.AppError):
        session.apply(FakeYDL(), ["safari", str(store), "bank"])
    # The doctor says which sites are signed in, from cookie names alone.
    store.write_bytes(b"cook")
    monkeypatch.setenv("VD_SAFARI_COOKIES", str(store))
    assert browser_session.status()["signed_in"] == {
        "youtube": True,
        "reddit": True,
        "instagram": True,
        "x": True,
    }


def test_an_info_json_never_keeps_cookie_values() -> None:
    from app.workers import session

    info = {
        "cookies": "a=1",
        "formats": [{"format_id": "1", "cookies": "SID=secret"}],
        "requested_formats": [{"cookies": "SID=secret"}],
    }
    cleaned = json.dumps(session.scrub(info))
    assert "secret" not in cleaned and "cookies" not in cleaned


def test_the_download_worker_hands_its_session_to_yt_dlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import download_worker, session

    seen: list[Any] = []

    def record(ydl: Any, spec: Any) -> int:
        seen.append(spec)
        raise errors.AppError(code="COOKIES_UNREADABLE")

    monkeypatch.setattr(session, "apply", record)
    request = {
        "url": URL,
        "mode": "mkv",
        "video_format_id": "v",
        "audio_format_ids": [],
        "subtitle_keys": [],
        "extras": {},
        "cookies_from_browser": ["safari", "/x"],
    }
    with pytest.raises(errors.AppError):
        download_worker._stream_pass(request, tmp_path, inspect_worker.Collector())
    assert seen == [["safari", "/x"]]


def test_reddit_goes_signed_in_first_only_while_the_setting_is_on(
    session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.reddit.com/r/videos/comments/abc/x/"
    settings_store.save(settings_store.Settings(safari_login=False))
    calls = fake_worker(monkeypatch, [info()])
    asyncio.run(inspect_service.inspect(url))
    assert calls == [None]


def test_a_sites_server_error_is_tried_once_more(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspect_service, "SERVER_ERROR_RETRY_SECONDS", 0)
    hiccup = errors.AppError(code="NETWORK", raw="HTTP Error 500: Internal Server Error")
    calls = fake_worker(monkeypatch, [hiccup, info()])
    asyncio.run(inspect_service.inspect("https://vimeo.com/1"))
    assert calls == [None, None]
    # Other network failures are not retried here (the job queue retries downloads itself).
    calls = fake_worker(monkeypatch, [errors.AppError(code="NETWORK", raw="timed out"), info()])
    with pytest.raises(errors.AppError):
        asyncio.run(inspect_service.inspect("https://vimeo.com/2"))
    assert calls == [None]
