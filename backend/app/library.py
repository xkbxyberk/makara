"""The catalogue of finished downloads, and keeping it honest about what is on disk.

Rules agreed with Berk:
* A record is never deleted because its file vanished. It is marked "missing" and, if the file
  turns up elsewhere with the same size and duration, re-linked automatically.
* The only destructive action is "move to Trash", and only for files the catalogue recorded.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app import errors, paths
from app.ffmpeg.probe import probe

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_items (
    id            TEXT PRIMARY KEY,
    job_id        TEXT,
    title         TEXT,
    source_url    TEXT,
    site          TEXT,
    channel       TEXT,
    upload_date   TEXT,
    mode          TEXT,
    kind          TEXT NOT NULL,           -- "video" | "audio"
    status        TEXT NOT NULL,           -- "ok" | "missing" | "trashed"
    primary_path  TEXT NOT NULL,
    size          INTEGER,
    duration      REAL,
    files         TEXT NOT NULL,           -- [{path, size, role}]
    tracks        TEXT NOT NULL,           -- {video: [...], audio: [...], subtitle: [...]}
    thumbnail     TEXT,                    -- a small JPEG in the app's data dir, for the grid
    added_at      REAL NOT NULL,
    checked_at    REAL
);
CREATE INDEX IF NOT EXISTS library_added ON library_items(added_at);
"""

JSON_COLUMNS = ("files", "tracks")
SORTS = {
    "added": "added_at DESC",
    "title": "title COLLATE NOCASE ASC",
    "size": "size DESC",
    "duration": "duration DESC",
    "uploaded": "upload_date DESC",
}
DURATION_TOLERANCE = 1.0  # seconds; remuxes can shift the container duration slightly
SPOTLIGHT_TIMEOUT = 10


def summarize_streams(path: Path) -> dict[str, Any]:
    """What a catalogue row needs to know about a media file, from ffprobe."""
    data = probe(path)
    tracks: dict[str, list[dict[str, Any]]] = {"video": [], "audio": [], "subtitle": []}
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind not in tracks or stream.get("disposition", {}).get("attached_pic"):
            continue
        tags = stream.get("tags") or {}
        tracks[kind].append(
            {
                "codec": stream.get("codec_name"),
                "language": tags.get("language"),
                "default": bool(stream.get("disposition", {}).get("default")),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "channels": stream.get("channels"),
            }
        )
    duration = data.get("format", {}).get("duration")
    return {"tracks": tracks, "duration": float(duration) if duration else None}


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for column in JSON_COLUMNS:
        out[column] = json.loads(out[column]) if out[column] else None
    return out


class Library:
    """Used from the event loop, the request threadpool and the scan thread at once.

    sqlite3 connections are not safe for concurrent use ("bad parameter or other API misuse"),
    so every statement goes through `_fetch`/`_write` under one lock. Slow work -- ffprobe,
    Spotlight -- happens outside the lock, so a scan never freezes the library screen.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._lock = threading.Lock()
        self._scan_lock = threading.Lock()
        with self._lock:
            conn.executescript(SCHEMA)

    def _fetch(self, sql: str, args: list[Any] | tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, args).fetchall())

    def _write(self, sql: str, args: list[Any] | tuple[Any, ...] = ()) -> None:
        with self._lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    # ---- writing ---------------------------------------------------------------------------
    def add(self, *, job: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any] | None:
        """Catalogue a finished job from what the worker reported (it already ran ffprobe)."""
        if outcome.get("separate"):
            added = None
            for output in outcome.get("outputs") or []:
                added = self.add(
                    job=job, outcome={**outcome, "outputs": [output], "separate": False}
                )
            return added
        files = outcome.get("outputs") or []
        primary = next(
            (f for f in files if f.get("role") == "primary"), files[0] if files else None
        )
        if primary is None:
            return None
        meta = outcome.get("meta") or {}
        tracks = primary.get("tracks") or {"video": [], "audio": [], "subtitle": []}
        if not tracks.get("video") and not tracks.get("audio"):
            return None  # e.g. a converted subtitle file: not something to play
        item = {
            "id": uuid.uuid4().hex[:12],
            "job_id": job["id"],
            "title": (Path(primary["path"]).stem if meta.get("extractor_key") == "Studio" else None)
            or meta.get("title")
            or job.get("title"),
            "source_url": meta.get("webpage_url") or job.get("source_url"),
            "site": meta.get("extractor_key"),
            "channel": meta.get("channel"),
            "upload_date": meta.get("upload_date"),
            "mode": job.get("mode"),
            "kind": "video" if tracks.get("video") else "audio",
            "status": "ok",
            "primary_path": primary["path"],
            "size": sum(int(f.get("size") or 0) for f in files),
            "duration": primary.get("duration") or meta.get("duration"),
            "files": [
                {"path": f["path"], "size": f.get("size"), "role": f.get("role")} for f in files
            ],
            "tracks": tracks,
            "thumbnail": primary.get("thumbnail"),
            "added_at": time.time(),
            "checked_at": time.time(),
        }
        columns = list(item)
        self._write(
            f"INSERT INTO library_items ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [json.dumps(item[c]) if c in JSON_COLUMNS else item[c] for c in columns],
        )
        return self.get(item["id"])

    def _update(self, item_id: str, **changes: Any) -> dict[str, Any] | None:
        assignments = ", ".join(f"{c} = ?" for c in changes)
        values = [json.dumps(v) if c in JSON_COLUMNS else v for c, v in changes.items()]
        self._write(f"UPDATE library_items SET {assignments} WHERE id = ?", [*values, item_id])
        return self.get(item_id)

    # ---- reading ---------------------------------------------------------------------------
    def get(self, item_id: str) -> dict[str, Any] | None:
        rows = self._fetch("SELECT * FROM library_items WHERE id = ?", [item_id])
        return _row(rows[0]) if rows else None

    def query(
        self,
        *,
        search: str = "",
        site: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        sort: str = "added",
        include_trashed: bool = False,
    ) -> list[dict[str, Any]]:
        where, args = [], []
        if search.strip():
            # Parameters, never string splicing; LIKE wildcards in the input are escaped.
            needle = (
                "%"
                + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            where.append("(title LIKE ? ESCAPE '\\' OR channel LIKE ? ESCAPE '\\')")
            args += [needle, needle]
        if site:
            where.append("site = ?")
            args.append(site)
        if kind in ("video", "audio"):
            where.append("kind = ?")
            args.append(kind)
        if status in ("ok", "missing", "trashed"):
            where.append("status = ?")
            args.append(status)
        elif not include_trashed:
            where.append("status != 'trashed'")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        order = SORTS.get(sort, SORTS["added"])
        rows = self._fetch(f"SELECT * FROM library_items {clause} ORDER BY {order}", args)
        return [r for r in (_row(row) for row in rows) if r is not None]

    def facets(self) -> dict[str, Any]:
        sites = [
            r[0]
            for r in self._fetch(
                "SELECT DISTINCT site FROM library_items "
                "WHERE site IS NOT NULL AND status != 'trashed' ORDER BY site"
            )
        ]
        [totals] = self._fetch(
            "SELECT COUNT(*), COALESCE(SUM(size), 0), "
            "SUM(CASE WHEN status = 'missing' THEN 1 ELSE 0 END) "
            "FROM library_items WHERE status != 'trashed'"
        )
        return {
            "sites": sites,
            "count": totals[0],
            "total_size": totals[1],
            "missing": totals[2] or 0,
        }

    # ---- keeping it true to the disk -----------------------------------------------------------
    def _owned(self, *, except_item: str | None = None) -> set[str]:
        """Every file (primary or sidecar) recorded by a live item, as resolved paths."""
        owned: set[str] = set()
        for row in self._fetch("SELECT id, files FROM library_items WHERE status != 'trashed'"):
            if row["id"] == except_item:
                continue
            owned.update(_resolved(f["path"]) for f in json.loads(row["files"] or "[]"))
        return owned

    def _mark(self, item_id: str, **changes: Any) -> None:
        """Scan updates never touch an item that was trashed while the scan was running."""
        assignments = ", ".join(f"{c} = ?" for c in changes)
        values = [json.dumps(v) if c in JSON_COLUMNS else v for c, v in changes.items()]
        self._write(
            f"UPDATE library_items SET {assignments} WHERE id = ? AND status != 'trashed'",
            [*values, item_id],
        )

    def scan(self, search_roots: list[Path]) -> dict[str, int]:
        """Mark vanished files missing; re-link any that turn up with the same size and duration.

        One scan at a time: the start-up scan and the button could otherwise race each other.
        """
        if not self._scan_lock.acquire(blocking=False):
            raise errors.AppError(code="SCAN_BUSY")
        try:
            return self._scan(search_roots)
        finally:
            self._scan_lock.release()

    def _scan(self, search_roots: list[Path]) -> dict[str, int]:
        counts = {"checked": 0, "missing": 0, "repaired": 0, "restored": 0}
        by_size: dict[int, list[Path]] | None = None
        items = self.query(include_trashed=False)
        # Downloading the same video twice gives two byte-identical files. Deleting one must not
        # re-point its record at the *other* item's file -- nor two records at one file.
        owned = self._owned()
        for item in items:
            counts["checked"] += 1
            primary = Path(item["primary_path"])
            size, duration = _primary_size(item), item.get("duration")
            # A download that finishes while this runs may reuse a deleted file's name, with the
            # same bytes; it is told apart by its creation time, not by its content.
            added = item.get("added_at")
            if primary.exists() and _same_media(primary, size, duration, born_before=added):
                if item["status"] == "missing":
                    counts["restored"] += 1
                self._mark(item["id"], status="ok", checked_at=time.time())
                continue
            # Gone -- or something else now sits at that path (a new download reused the name).
            if by_size is None:
                by_size = _index_by_size(search_roots)
            found = find_moved(primary, size, duration, by_size, exclude=owned, born_before=added)
            if found is not None:
                owned.add(_resolved(found))
                files = [
                    {**f, "path": str(found)} if f["path"] == item["primary_path"] else f
                    for f in item["files"]
                ]
                self._mark(
                    item["id"],
                    primary_path=str(found),
                    files=files,
                    status="ok",
                    checked_at=time.time(),
                )
                counts["repaired"] += 1
            else:
                self._mark(item["id"], status="missing", checked_at=time.time())
                counts["missing"] += 1
        return counts

    # ---- user actions ----------------------------------------------------------------------
    def trash(self, item_id: str) -> dict[str, Any]:
        """Move an item's files to the macOS Trash (recoverable) and mark it trashed.

        Only files that are still *this item's*: present, the size that was recorded, and not
        recorded by any other live item. A path reused by a later download is left alone.
        """
        item = self.get(item_id)
        if item is None:
            raise errors.AppError(code="ITEM_NOT_FOUND", raw=item_id)
        if item["status"] != "ok":
            raise errors.AppError(code="ITEM_NOT_TRASHABLE", raw=item["status"])
        others = self._owned(except_item=item_id)

        def ours(file: dict[str, Any]) -> bool:
            path = Path(file["path"])
            if not path.is_file() or _resolved(path) in others:
                return False
            return not file.get("size") or path.stat().st_size == int(file["size"])

        primary = next((f for f in item["files"] if f["path"] == item["primary_path"]), None)
        if primary is None or not ours(primary):
            raise errors.AppError(code="FILE_MISSING", raw=item["primary_path"])
        try:
            move_to_trash(Path(primary["path"]))
        except OSError as exc:
            raise errors.AppError(code="TRASH_FAILED", raw=str(exc)) from None
        for file in item["files"]:
            if file is not primary and ours(file):
                with contextlib.suppress(OSError):
                    move_to_trash(Path(file["path"]))
        updated = self._update(item_id, status="trashed", checked_at=time.time())
        assert updated is not None
        return updated

    def thumbnail(self, item_id: str) -> Path | None:
        """Only ever a file inside the app's own thumbnail folder."""
        item = self.get(item_id)
        if item is None or not item.get("thumbnail"):
            return None
        folder = (paths.data_dir() / "thumbs").resolve()
        path = Path(item["thumbnail"]).resolve()
        return path if path.parent == folder and path.is_file() else None

    def existing_primary(self, item_id: str) -> Path:
        item = self.get(item_id)
        if item is None:
            raise errors.AppError(code="ITEM_NOT_FOUND", raw=item_id)
        path = Path(item["primary_path"])
        if item["status"] == "trashed" or not path.exists():
            raise errors.AppError(code="FILE_MISSING", raw=str(path))
        return path


def move_to_trash(path: Path) -> None:
    """The macOS Trash -- recoverable. In fixture mode (the e2e suite drives the real server)
    files go to a folder inside the app's data dir instead, so tests never fill the real Trash."""
    if paths.fixture_mode():
        target = paths.data_dir() / "simulated-trash"
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), target / f"{uuid.uuid4().hex[:6]}-{path.name}")
        return
    from send2trash import send2trash

    send2trash(str(path))


def _resolved(path: str | Path) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(path)


def _born_after(path: Path, moment: float | None) -> bool:
    """Was this file created after `moment`? macOS keeps a file's creation time through moves,
    renames, Finder tags and Put Back, so a file born after an item was catalogued cannot be
    that item's file -- it is a later download that happens to be byte-identical."""
    if moment is None:
        return False
    born = getattr(path.stat(), "st_birthtime", None)
    return born is not None and born > moment


def _same_media(
    path: Path, size: int | None, duration: float | None, born_before: float | None = None
) -> bool:
    """Is the file at `path` still the one that was recorded? Size must match exactly; the
    duration too when it is known; and it must not be younger than the record."""
    try:
        if _born_after(path, born_before):
            return False
        if size and path.stat().st_size != size:
            return False
        if duration is not None:
            probed = summarize_streams(path)["duration"]
            return probed is not None and abs(probed - duration) <= DURATION_TOLERANCE
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return True


def _primary_size(item: dict[str, Any]) -> int | None:
    for file in item.get("files") or []:
        if file["path"] == item["primary_path"]:
            return int(file["size"]) if file.get("size") else None
    return None


def _index_by_size(roots: list[Path]) -> dict[int, list[Path]]:
    index: dict[int, list[Path]] = {}
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]  # skips .vd-work too
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    index.setdefault(path.stat().st_size, []).append(path)
                except OSError:
                    continue
    return index


def _hidden_or_ours(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts[1:]):  # .Trash, .Trashes, .vd-work, ...
        return True
    if "Backups.backupdb" in path.parts or "MobileBackups" in path.parts:
        return True
    return _resolved(path).startswith(_resolved(paths.data_dir()))  # e.g. simulated-trash


def _spotlight(name: str) -> list[Path]:
    """Files anywhere on the Mac with exactly this name, via Spotlight. argv only, no shell."""
    if sys.platform != "darwin" or paths.fixture_mode() or not shutil.which("mdfind"):
        return []
    try:
        out = subprocess.run(
            ["mdfind", "-name", name],
            capture_output=True,
            text=True,
            timeout=SPOTLIGHT_TIMEOUT,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = [Path(line) for line in out.splitlines() if line and Path(line).name == name]
    return [p for p in found if not _hidden_or_ours(p)][:50]


def find_moved(
    original: Path,
    size: int | None,
    duration: float | None,
    by_size: dict[int, list[Path]],
    exclude: set[str] | None = None,
    born_before: float | None = None,
) -> Path | None:
    """A candidate must match the recorded size exactly *and* the duration, so a different file
    that happens to share a name (or a size) is never mistaken for the one that moved. A file
    created after the record cannot be it either (see `_born_after`)."""
    if not size:
        return None
    candidates = list(by_size.get(size, []))
    candidates += [p for p in _spotlight(original.name) if p not in candidates]
    for candidate in candidates:
        # Compare resolved paths: a symlinked folder must not disguise another item's file.
        if exclude and _resolved(candidate) in exclude:
            continue
        try:
            if _born_after(candidate, born_before):
                continue
            if candidate.stat().st_size != size:
                continue
            if duration is not None:
                probed = summarize_streams(candidate)["duration"]
                if probed is None or abs(probed - duration) > DURATION_TOLERANCE:
                    continue
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        return candidate
    return None
