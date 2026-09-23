from __future__ import annotations

import pytest

from app import errors
from app.ytdlp import command


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: [vimeo] Use --cookies to provide account credentials", "LOGIN_REQUIRED"),
        ("Video unavailable. This video has been removed", "VIDEO_UNAVAILABLE"),
        ("This video is DRM protected", "DRM_PROTECTED"),
        ("Sign in to confirm your age", "AGE_RESTRICTED"),
        ("The uploader has not made this video available in your country", "GEO_RESTRICTED"),
        ("ERROR: Unsupported URL: https://example.com/x", "UNSUPPORTED_SITE"),
        ("No supported JavaScript runtime could be found", "NO_JS_RUNTIME"),
        ("Unable to download webpage: <urlopen error timed out>", "NETWORK"),
        ("something we have never seen", "UNKNOWN"),
    ],
)
def test_classify(message: str, expected: str) -> None:
    assert errors.classify(message) == expected


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


def test_quote_never_builds_a_shell_string_with_unescaped_input() -> None:
    quoted = command.quote(["yt-dlp", "https://x/y?a=b&rm=-rf /"])
    assert quoted == "yt-dlp 'https://x/y?a=b&rm=-rf /'"
