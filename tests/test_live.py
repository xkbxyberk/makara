"""Opt-in live smoke tests. Never part of scripts/check.sh.

    RUN_LIVE_TESTS=1 uv run pytest -m live -v

They hit YouTube for real. The download test fetches the *smallest* video and audio formats
(roughly 30 MB), so it stays quick while still exercising two real audio languages.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to hit the network"
    ),
]

MULTI_AUDIO_URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"


@pytest.fixture
def live_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("VD_FIXTURE_MODE", raising=False)
    monkeypatch.setenv("VD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VD_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    return tmp_path


def test_inspect_a_real_multi_audio_video(live_env: Path) -> None:
    from app.inspect_service import inspect

    model = asyncio.run(inspect(MULTI_AUDIO_URL))
    assert model["kind"] == "video"
    assert len(model["audio_languages"]) > 1
    assert any(group["role"] == "original" for group in model["audio_languages"])
    assert "NO_JS_RUNTIME" not in model["warnings"]


def _smallest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    https = [r for r in rows if not r["is_manifest"] and r.get("filesize")] or rows
    return min(https, key=lambda r: r.get("filesize") or r.get("tbr") or 0)


def test_download_a_real_video_with_two_audio_languages(live_env: Path) -> None:
    from app import inspect_service
    from app.ffmpeg.probe import probe
    from app.jobs import planning
    from app.settings import Settings
    from app.workers import download_worker

    model = asyncio.run(inspect_service.inspect(MULTI_AUDIO_URL))
    groups = {g["language"]: g for g in model["audio_languages"]}
    original = next(g for g in model["audio_languages"] if g["role"] == "original")
    turkish = groups.get("tr") or next(g for g in model["audio_languages"] if g is not original)
    selection = {
        "mode": "mkv",
        "video_format_id": _smallest(model["video_formats"])["format_id"],
        "audio_format_ids": [
            _smallest(original["tracks"])["format_id"],
            _smallest(turkish["tracks"])["format_id"],
        ],
        "subtitle_keys": [],
        "extras": {"thumbnail": False},
    }
    entry = inspect_service.recall(model["inspect_id"])
    job = planning.build_job(entry, selection, Settings(download_dir=str(live_env / "downloads")))

    buffer = io.StringIO()
    download_worker.OUT = buffer
    assert download_worker.run(job["request"]) == 0, buffer.getvalue()[-2000:]
    done = [json.loads(line) for line in buffer.getvalue().splitlines() if '"t": "done"' in line]
    [output] = [Path(f) for f in done[-1]["files"]]

    audio = [s for s in probe(output)["streams"] if s["codec_type"] == "audio"]
    assert len(audio) == 2
    assert [s["disposition"]["default"] for s in audio] == [1, 0]
    assert audio[1]["tags"]["language"] in ("tur", turkish["language"][:3])
