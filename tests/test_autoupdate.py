"""The weekly background yt-dlp update (P6e), without touching the real environment."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app import autoupdate, paths, system


class Manager:
    def __init__(self, active: set[str] | None = None) -> None:
        self.active = active or set()
        self.hold = False
        self.held_during_update: bool | None = None
        self.woken = 0

    def wake(self) -> None:
        self.woken += 1


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Outside fixture mode, with an updater that only records that it ran."""
    monkeypatch.setattr(paths, "fixture_mode", lambda: False)
    ran: list[str] = []

    def fake_update() -> dict[str, Any]:
        ran.append("update")
        return {"before": {"version": "1"}, "after": {"version": "2"}, "changed": True, "log": ""}

    monkeypatch.setattr(system, "update_ytdlp", fake_update)
    return ran


def test_it_updates_once_a_week_and_holds_the_queue_meanwhile(
    real_mode: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = Manager()
    real = system.update_ytdlp

    def watching() -> dict[str, Any]:
        manager.held_during_update = manager.hold
        return real()

    monkeypatch.setattr(system, "update_ytdlp", watching)
    record = asyncio.run(autoupdate.run_once(manager))
    assert record is not None and record["ok"] is True and record["version"] == "2"
    assert manager.held_during_update is True and manager.hold is False and manager.woken == 1
    assert autoupdate.last()["version"] == "2"
    # Not again within the week.
    assert asyncio.run(autoupdate.run_once(manager)) is None
    assert real_mode == ["update"]
    assert autoupdate.due(time.time() + autoupdate.INTERVAL_SECONDS + 1)


def test_it_waits_while_something_downloads(real_mode: list[str]) -> None:
    assert asyncio.run(autoupdate.run_once(Manager(active={"job1"}))) is None
    assert real_mode == []


def test_never_in_fixture_mode_nor_when_turned_off(
    real_mode: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import settings as settings_store

    settings_store.save(settings_store.Settings(auto_update_ytdlp=False))
    assert not autoupdate.due()
    settings_store.save(settings_store.Settings(auto_update_ytdlp=True))
    monkeypatch.setattr(paths, "fixture_mode", lambda: True)
    assert not autoupdate.due()
    assert real_mode == []
