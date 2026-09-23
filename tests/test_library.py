from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app.library import Library, summarize_streams


@pytest.fixture
def library() -> Library:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return Library(conn)


def outcome_for(
    path: Path,
    *,
    title: str = "Local test clip",
    channel: str = "VD Test Channel",
    extra: list[Path] | None = None,
) -> dict[str, Any]:
    summary = summarize_streams(path)
    outputs = [{"path": str(path), "size": path.stat().st_size, "role": "primary", **summary}]
    for other in extra or []:
        outputs.append({"path": str(other), "size": other.stat().st_size, "role": "sidecar"})
    return {
        "outputs": outputs,
        "meta": {
            "title": title,
            "channel": channel,
            "extractor_key": "Generic",
            "webpage_url": "https://example.test/local-media",
            "upload_date": "20260901",
        },
    }


def add(library: Library, path: Path, **kwargs: Any) -> dict[str, Any]:
    item = library.add(
        job={"id": "job1", "mode": "mkv", "title": None}, outcome=outcome_for(path, **kwargs)
    )
    assert item is not None
    return item


@pytest.fixture
def clip(tmp_path: Path, test_media: Path) -> Path:
    root = tmp_path / "downloads" / "Generic" / "VD Test Channel"
    root.mkdir(parents=True)
    target = root / "clip.mp4"
    shutil.copy2(test_media / "video_h264.mp4", target)
    return target


def test_a_finished_job_becomes_a_catalogue_row(library: Library, clip: Path) -> None:
    item = add(library, clip)
    assert item["status"] == "ok"
    assert item["kind"] == "video"
    assert item["tracks"]["video"][0]["codec"] == "h264"
    assert item["duration"] == pytest.approx(4, abs=0.3)
    assert item["site"] == "Generic" and item["channel"] == "VD Test Channel"


def test_audio_files_are_catalogued_as_audio(
    library: Library, tmp_path: Path, test_media: Path
) -> None:
    song = tmp_path / "song.m4a"
    shutil.copy2(test_media / "audio_tr.m4a", song)
    assert add(library, song)["kind"] == "audio"


def test_search_sort_and_filters(library: Library, tmp_path: Path, test_media: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.m4a"
    shutil.copy2(test_media / "video_h264.mp4", a)
    shutil.copy2(test_media / "audio_en.m4a", b)
    add(library, a, title="Zebra 100% documentary")
    add(library, b, title="apple song", channel="Music_Channel")
    assert [i["title"] for i in library.query(sort="title")] == [
        "apple song",
        "Zebra 100% documentary",
    ]
    assert [i["title"] for i in library.query(search="zebra")] == ["Zebra 100% documentary"]
    # LIKE wildcards typed by the user are literal characters, not patterns.
    assert [i["title"] for i in library.query(search="100%")] == ["Zebra 100% documentary"]
    assert library.query(search="_") and all(
        "_" in (i["channel"] or "") for i in library.query(search="_")
    )
    assert [i["kind"] for i in library.query(kind="audio")] == ["audio"]
    assert library.facets()["count"] == 2


def test_a_deleted_file_is_marked_missing_never_forgotten(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    item = add(library, clip)
    clip.unlink()
    counts = library.scan([tmp_path / "downloads"])
    assert counts["missing"] == 1
    assert library.get(item["id"])["status"] == "missing"  # type: ignore[index]
    assert library.facets()["missing"] == 1


def test_a_moved_file_is_relinked_by_size_and_duration(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    item = add(library, clip)
    moved = tmp_path / "downloads" / "Elsewhere" / "renamed.mp4"
    moved.parent.mkdir(parents=True)
    clip.rename(moved)
    counts = library.scan([tmp_path / "downloads"])
    assert counts["repaired"] == 1
    relinked = library.get(item["id"])
    assert relinked is not None and relinked["primary_path"] == str(moved)
    assert relinked["status"] == "ok"


def test_a_same_size_file_with_another_duration_is_not_mistaken(
    library: Library, clip: Path, tmp_path: Path, test_media: Path
) -> None:
    item = add(library, clip)
    impostor = tmp_path / "downloads" / "impostor.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            "-c:a",
            "aac",
            str(impostor),
        ],
        check=True,
    )
    # Same byte count, different media (1 s, not 4 s): pad the impostor to the clip's size.
    with impostor.open("ab") as f:
        f.write(b"\0" * (clip.stat().st_size - impostor.stat().st_size))
    clip.unlink()
    library.scan([tmp_path / "downloads"])
    assert library.get(item["id"])["status"] == "missing"  # type: ignore[index]


def test_a_file_that_comes_back_is_restored(library: Library, clip: Path, tmp_path: Path) -> None:
    item = add(library, clip)
    hidden = clip.with_name("hidden.bin")
    clip.rename(hidden)
    hidden.write_bytes(hidden.read_bytes() + b"x")  # size changed, so no false re-link
    library.scan([tmp_path / "nowhere"])
    hidden.write_bytes(hidden.read_bytes()[:-1])
    hidden.rename(clip)
    assert library.scan([tmp_path / "downloads"])["restored"] == 1
    assert library.get(item["id"])["status"] == "ok"  # type: ignore[index]


def test_trash_moves_every_file_of_the_item_to_the_trash(
    library: Library, clip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trash = tmp_path / "Trash"
    trash.mkdir()
    fake = types.ModuleType("send2trash")
    fake.send2trash = lambda p: shutil.move(p, trash / Path(p).name)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "send2trash", fake)  # never touch the real ~/.Trash
    sidecar = clip.with_suffix(".tr.srt")
    sidecar.write_text("1\n00:00:00,000 --> 00:00:01,000\nMerhaba\n")
    item = add(library, clip, extra=[sidecar])
    trashed = library.trash(item["id"])
    assert trashed["status"] == "trashed"
    assert not clip.exists() and not sidecar.exists()
    assert sorted(p.name for p in trash.iterdir()) == ["clip.mp4", "clip.tr.srt"]
    assert library.query() == []  # hidden from the library by default
    assert len(library.query(include_trashed=True)) == 1  # but the history is kept


def test_concurrent_use_from_many_threads_is_safe(library: Library, clip: Path) -> None:
    """The library is hit from the event loop, the request threadpool and the scan thread."""
    import threading

    item = add(library, clip)
    failures: list[BaseException] = []

    def hammer() -> None:
        try:
            for _ in range(200):
                library.query(search="clip")
                library.facets()
                library._update(item["id"], checked_at=1.0)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
