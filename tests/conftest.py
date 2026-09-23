from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "infojson"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


@pytest.fixture(scope="session")
def multi_audio() -> dict[str, Any]:
    return load_fixture("youtube_multi_audio")


@pytest.fixture(scope="session")
def many_subs() -> dict[str, Any]:
    return load_fixture("youtube_many_subs")


@pytest.fixture(scope="session")
def playlist() -> dict[str, Any]:
    return load_fixture("youtube_playlist_flat")


@pytest.fixture(scope="session")
def other_site() -> dict[str, Any]:
    return load_fixture("other_site")
