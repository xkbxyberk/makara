"""Filenames come from video titles, which are untrusted input. None may escape the root."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from app import errors
from app.ytdlp import naming

TEMPLATE = "%(channel)s/%(title)s.%(ext)s"


@pytest.mark.parametrize("title", ["..", ".", "", "  ..  ", "../../etc/passwd", ".hidden"])
def test_a_hostile_title_stays_inside_the_root(tmp_path: Path, title: str) -> None:
    rel = naming.render_relative(TEMPLATE, {"channel": "Ch", "title": title}, "mkv")
    assert all(part not in ("", ".", "..") for part in rel.parts)
    assert not rel.parts[-1].startswith(".")
    [target] = naming.claim(tmp_path / "root", rel, [".mkv"])
    assert target.resolve().is_relative_to((tmp_path / "root").resolve())
    assert target.resolve() != (tmp_path / "root").resolve()


def test_a_hostile_channel_stays_inside_the_root(tmp_path: Path) -> None:
    rel = naming.render_relative(TEMPLATE, {"channel": "..", "title": "t"}, "mkv")
    [target] = naming.claim(tmp_path / "root", rel, [".mkv"])
    assert target.parent.parent == (tmp_path / "root").resolve()


def test_a_literal_parent_directory_in_the_template_is_refused() -> None:
    for template in ("../%(title)s.%(ext)s", "a/../../%(title)s.%(ext)s", "./%(title)s"):
        with pytest.raises(errors.AppError) as caught:
            naming.render_relative(template, {"title": "t"}, "mkv")
        assert caught.value.code == "PATH_OUTSIDE_ROOT"


def test_long_titles_are_trimmed_below_the_filesystem_limit(tmp_path: Path) -> None:
    title = "ş" * 400  # 800 bytes in UTF-8
    rel = naming.render_relative(TEMPLATE, {"channel": "Ch", "title": title}, "mkv")
    assert len(rel.parts[-1].encode()) <= naming.MAX_COMPONENT_BYTES
    targets = naming.claim(tmp_path, rel, [".description.txt", ".mkv"])
    assert all(t.exists() and len(t.name.encode()) <= 255 for t in targets)


def test_claim_reserves_one_base_name_for_the_whole_set(tmp_path: Path) -> None:
    rel = PurePosixPath("Ch/Clip")
    first = naming.claim(tmp_path, rel, [".mp4", ".en.m4a", ".tr.srt"])
    second = naming.claim(tmp_path, rel, [".mp4", ".en.m4a", ".tr.srt"])
    assert [p.name for p in second] == ["Clip (2).mp4", "Clip (2).en.m4a", "Clip (2).tr.srt"]
    # One file of the set already taken moves the *whole* set to the next free base.
    (tmp_path / "Ch" / "Clip (3).tr.srt").write_text("mine")
    third = naming.claim(tmp_path, rel, [".mp4", ".tr.srt"])
    assert [p.name for p in third] == ["Clip (4).mp4", "Clip (4).tr.srt"]
    assert (tmp_path / "Ch" / "Clip (3).tr.srt").read_text() == "mine"
    assert not (tmp_path / "Ch" / "Clip (3).mp4").exists()  # partial claims are rolled back
    assert all(p.exists() for p in first)


def test_claim_never_follows_a_symlink_out_of_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "Ch")
    with pytest.raises(errors.AppError) as caught:
        naming.claim(root, PurePosixPath("Ch/Clip"), [".mkv"])
    assert caught.value.code == "PATH_OUTSIDE_ROOT"
    assert list(outside.iterdir()) == []


def test_release_removes_only_empty_placeholders(tmp_path: Path) -> None:
    [a, b] = naming.claim(tmp_path, PurePosixPath("x"), [".mkv", ".jpg"])
    b.write_bytes(b"real data")
    naming.release([a, b])
    assert not a.exists() and b.read_bytes() == b"real data"
