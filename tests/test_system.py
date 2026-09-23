from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app import system


class FakeBoard:
    def __init__(self) -> None:
        self.count = 0
        self.value: str | None = None

    def changeCount(self) -> int:
        return self.count

    def text(self) -> str | None:
        return self.value

    def copy(self, value: str) -> None:
        self.value = value
        self.count += 1


def test_clipboard_watcher_offers_new_links_only_while_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system, "CLIPBOARD_POLL_SECONDS", 0.01)
    board = FakeBoard()
    board.copy("https://already.there/before-enabling")
    enabled = {"on": True}
    published: list[dict[str, Any]] = []

    async def scenario() -> None:
        watcher = system.ClipboardWatcher(lambda: enabled["on"], published.append, board=board)
        watcher.start()
        await asyncio.sleep(0.05)  # what was on the clipboard before is ignored
        board.copy("not a link")
        await asyncio.sleep(0.05)
        board.copy("https://www.youtube.com/watch?v=abc")
        await asyncio.sleep(0.05)
        enabled["on"] = False
        board.copy("https://example.com/while-disabled")
        await asyncio.sleep(0.05)
        watcher.stop()

    asyncio.run(scenario())
    assert published == [{"type": "clipboard", "url": "https://www.youtube.com/watch?v=abc"}]
