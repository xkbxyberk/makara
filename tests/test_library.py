from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app import errors
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


def test_the_sidebar_shelves_videos_music_and_studio_output(
    library: Library, tmp_path: Path, test_media: Path
) -> None:
    video, song, cut = tmp_path / "v.mp4", tmp_path / "s.m4a", tmp_path / "v (kesit).mp4"
    shutil.copy2(test_media / "video_h264.mp4", video)
    shutil.copy2(test_media / "audio_en.m4a", song)
    shutil.copy2(test_media / "video_h264.mp4", cut)
    add(library, video, title="A video")
    add(library, song, title="A song")
    studio = outcome_for(cut, title="ignored")
    studio["meta"]["extractor_key"] = "Studio"
    library.add(job={"id": "job2", "mode": "studio", "title": None}, outcome=studio)
    # A Stüdyo cut is a video, but it is on the Stüdyo shelf, not with the downloads.
    assert [i["title"] for i in library.query(category="videos")] == ["A video"]
    assert [i["title"] for i in library.query(category="music")] == ["A song"]
    assert [i["title"] for i in library.query(category="studio")] == ["v (kesit)"]
    assert library.facets()["categories"] == {"videos": 1, "music": 1, "studio": 1}


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


# ---- regression tests for the M3 adversarial review ------------------------------------------


def _two_identical(
    library: Library, tmp_path: Path, test_media: Path
) -> tuple[Path, Path, str, str]:
    root = tmp_path / "downloads"
    root.mkdir(exist_ok=True)
    a, b = root / "A.mp4", root / "B.mp4"
    shutil.copy2(test_media / "video_h264.mp4", a)
    shutil.copy2(test_media / "video_h264.mp4", b)
    return a, b, add(library, a)["id"], add(library, b)["id"]


def test_two_missing_items_never_end_up_sharing_one_file(
    library: Library, tmp_path: Path, test_media: Path
) -> None:
    a, b, a_id, b_id = _two_identical(library, tmp_path, test_media)
    moved = tmp_path / "downloads" / "sub" / "A.mp4"
    moved.parent.mkdir()
    a.rename(moved)
    b.unlink()
    counts = library.scan([tmp_path / "downloads"])
    assert counts["repaired"] == 1 and counts["missing"] == 1
    paths = [library.get(i)["primary_path"] for i in (a_id, b_id)]  # type: ignore[index]
    assert len(set(paths)) == 2, "two records point at one file"


def test_a_different_file_at_the_old_path_is_not_restored(
    library: Library, clip: Path, tmp_path: Path, test_media: Path
) -> None:
    item = add(library, clip)
    clip.unlink()
    shutil.copy2(test_media / "audio_en.m4a", clip)  # a later download reused the name
    library.scan([tmp_path / "downloads"])
    assert library.get(item["id"])["status"] == "missing"  # type: ignore[index]


def test_trash_refuses_an_item_that_is_not_ok(
    library: Library, clip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.library

    monkeypatch.setattr(app.library, "move_to_trash", lambda p: p.unlink())
    item = add(library, clip)
    library.trash(item["id"])
    with pytest.raises(errors.AppError) as caught:
        library.trash(item["id"])  # a double click, or a stale tab
    assert caught.value.code == "ITEM_NOT_TRASHABLE"


def test_trash_leaves_a_file_that_is_no_longer_ours(
    library: Library, clip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.library

    trashed: list[Path] = []
    monkeypatch.setattr(app.library, "move_to_trash", lambda p: trashed.append(p) or p.unlink())
    sidecar = clip.with_suffix(".tr.srt")
    sidecar.write_text("1\n00:00:00,000 --> 00:00:01,000\nİlk\n")
    item = add(library, clip, extra=[sidecar])
    sidecar.write_text("a different, newer subtitle that now sits at this path\n")
    library.trash(item["id"])
    assert trashed == [clip]
    assert sidecar.exists()


def test_trash_never_touches_a_file_another_item_owns(
    library: Library, tmp_path: Path, test_media: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.library

    trashed: list[Path] = []
    monkeypatch.setattr(app.library, "move_to_trash", lambda p: trashed.append(p))
    a, _, _a_id, b_id = _two_identical(library, tmp_path, test_media)
    # Force B's record to also list A's file as a sidecar (e.g. a stale re-link).
    b = library.get(b_id)
    assert b is not None
    library._update(
        b_id, files=[*b["files"], {"path": str(a), "size": a.stat().st_size, "role": "sidecar"}]
    )
    library.trash(b_id)
    assert a not in trashed


def test_a_scan_never_resurrects_an_item_trashed_meanwhile(library: Library, clip: Path) -> None:
    item = add(library, clip)
    library._update(item["id"], status="trashed")
    library._mark(item["id"], status="missing")  # what a slow, concurrent scan would do
    assert library.get(item["id"])["status"] == "trashed"  # type: ignore[index]


def test_only_one_scan_runs_at_a_time(library: Library, tmp_path: Path) -> None:
    library._scan_lock.acquire()
    try:
        with pytest.raises(errors.AppError) as caught:
            library.scan([tmp_path])
        assert caught.value.code == "SCAN_BUSY"
    finally:
        library._scan_lock.release()


def test_a_symlinked_root_does_not_disguise_another_items_file(
    library: Library, tmp_path: Path, test_media: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    p, q = real / "P.mp4", real / "Q.mp4"
    shutil.copy2(test_media / "video_h264.mp4", p)
    shutil.copy2(test_media / "video_h264.mp4", q)
    add(library, p)
    q_id = add(library, q)["id"]
    link = tmp_path / "link"
    link.symlink_to(real)
    q.unlink()
    library.scan([link])  # the walk sees link/P.mp4, which *is* P's file
    assert library.get(q_id)["status"] == "missing"  # type: ignore[index]


def test_spotlight_candidates_from_the_trash_or_hidden_folders_are_ignored() -> None:
    from app import paths
    from app.library import _hidden_or_ours

    home = Path.home()
    assert _hidden_or_ours(home / ".Trash" / "clip.mp4")
    assert _hidden_or_ours(Path("/Volumes/Disk/.Trashes/501/clip.mp4"))
    assert _hidden_or_ours(home / "Movies" / "VideoDownloader" / ".vd-work" / "x" / "clip.mp4")
    assert _hidden_or_ours(paths.data_dir() / "simulated-trash" / "clip.mp4")
    assert _hidden_or_ours(Path("/Volumes/TM/Backups.backupdb/mac/clip.mp4"))
    assert not _hidden_or_ours(home / "Movies" / "clip.mp4")


def test_an_identical_later_download_at_the_old_path_is_not_restored(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    """Deleted in Finder, then the same video downloaded again: the new download gets the freed
    name and the very same bytes. It is the new download's file, not a resurrected old one."""
    item = add(library, clip)
    data = clip.read_bytes()
    clip.unlink()
    clip.write_bytes(data)  # a new file, created after the item was catalogued
    library.scan([tmp_path / "downloads"])
    assert library.get(item["id"])["status"] == "missing"  # type: ignore[index]


def test_an_identical_later_download_elsewhere_is_not_a_relink(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    item = add(library, clip)
    data = clip.read_bytes()
    clip.unlink()
    later = tmp_path / "downloads" / "Channel" / f"{clip.stem} (2){clip.suffix}"
    later.parent.mkdir(parents=True, exist_ok=True)
    later.write_bytes(data)  # finished while the scan ran, not yet in the catalogue
    counts = library.scan([tmp_path / "downloads"])
    assert counts["repaired"] == 0 and counts["missing"] == 1
    assert library.get(item["id"])["primary_path"] == str(clip)  # type: ignore[index]


# ---- removing a missing record (Berk's request, 2026-10-13) ---------------------------------
def test_a_missing_record_can_be_removed_and_nothing_on_disk_is_touched(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    item = add(library, clip)
    gone = tmp_path / "elsewhere.mp4"
    clip.rename(gone)  # Berk deleted (or moved) it in Finder
    library.scan([tmp_path / "nowhere"])
    assert library.get(item["id"])["status"] == "missing"
    library.forget(item["id"])
    assert library.get(item["id"]) is None
    assert gone.exists()  # the record went, the file was never looked at again
    assert library.facets()["missing"] == 0


def test_a_record_whose_file_is_back_is_not_removed(
    library: Library, clip: Path, tmp_path: Path
) -> None:
    item = add(library, clip)
    hidden = tmp_path / "hidden.mp4"
    clip.rename(hidden)
    library.scan([tmp_path / "nowhere"])
    hidden.rename(clip)  # put back before the click
    with pytest.raises(errors.AppError) as caught:
        library.forget(item["id"])
    assert caught.value.code == "ITEM_NOT_MISSING"
    assert library.get(item["id"]) is not None
    # And an item that is fine is never "forgotten".
    other = add(library, clip, title="Fine")
    with pytest.raises(errors.AppError):
        library.forget(other["id"])


def test_removing_every_missing_record_keeps_the_ones_that_came_back(
    library: Library, clip: Path, tmp_path: Path, test_media: Path
) -> None:
    first = add(library, clip)
    second_path = clip.parent / "second.mp4"
    shutil.copy2(test_media / "video_h264.mp4", second_path)
    second = add(library, second_path, title="Second")
    clip.rename(tmp_path / "a.mp4")
    second_path.rename(tmp_path / "b.mp4")
    library.scan([tmp_path / "nowhere"])
    (tmp_path / "b.mp4").rename(second_path)  # one comes back
    assert library.forget_missing() == {"removed": 1, "kept": 1}
    assert library.get(first["id"]) is None
    assert library.get(second["id"]) is not None
