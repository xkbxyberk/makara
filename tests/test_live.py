"""Opt-in live smoke test. Never runs in scripts/check.sh."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to hit the network"
)


@pytest.mark.live
def test_inspect_a_real_multi_audio_video() -> None:
    import asyncio

    from app import paths
    from app.inspect_service import inspect

    assert not paths.fixture_mode(), "unset VD_FIXTURE_MODE for the live test"
    model = asyncio.run(inspect("https://www.youtube.com/watch?v=0e3GPea1Tyg"))
    assert model["kind"] == "video"
    assert len(model["audio_languages"]) > 1
    assert any(group["role"] == "original" for group in model["audio_languages"])
