"""The catalogue of finished downloads, and keeping it honest about what is on disk.

Rules agreed with Berk:
* A record is never deleted because its file vanished. It is marked "missing" and, if the file
  turns up elsewhere with the same size and duration, re-linked automatically.
* The only destructive action is "move to Trash", and only for files the catalogue recorded.
"""

from __future__ import annotations

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
        files = outcome.get("outputs") or []
        primary = next(
            (f for f in files if f.get("role") == "primary"), files[0] if files else None
        )
        if primary is None:
            return None
        meta = outcome.get("meta") or {}
        tracks = primary.get("tracks") or {"video": [], "audio": [], "subtitle": []}
        item = {
            "id": uuid.uuid4().hex[:12],
            "job_id": job["id"],
            "title": meta.get("title") or job.get("title"),
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
    def scan(self, search_roots: list[Path]) -> dict[str, int]:
        """Mark vanished files missing; re-link any that turn up with the same size and duration."""
        counts = {"checked": 0, "missing": 0, "repaired": 0, "restored": 0}
        by_size: dict[int, list[Path]] | None = None
        items = self.query(include_trashed=False)
        # Downloading the same video twice gives two byte-identical files. Deleting one must not
        # re-point its record at the *other* item's file.
        owned = {str(Path(i["primary_path"])) for i in items}
        for item in items:
            counts["checked"] += 1
            primary = Path(item["primary_path"])
            if primary.exists():
                if item["status"] == "missing":
                    counts["restored"] += 1
                self._update(item["id"], status="ok", checked_at=time.time())
                continue
            if by_size is None:
                by_size = _index_by_size(search_roots)
            found = find_moved(
                primary, _primary_size(item), item.get("duration"), by_size, exclude=owned
            )
            if found is not None:
                files = [
                    {**f, "path": str(found)} if f["path"] == item["primary_path"] else f
                    for f in item["files"]
                ]
                self._update(
                    item["id"],
                    primary_path=str(found),
                    files=files,
                    status="ok",
                    checked_at=time.time(),
                )
                counts["repaired"] += 1
            else:
                self._update(item["id"], status="missing", checked_at=time.time())
                counts["missing"] += 1
        return counts

    # ---- user actions ----------------------------------------------------------------------
    def trash(self, item_id: str) -> dict[str, Any]:
        """Move every file of an item to the macOS Trash (recoverable) and mark it trashed."""
        item = self.get(item_id)
        if item is None:
            raise errors.AppError(code="ITEM_NOT_FOUND", raw=item_id)
        for file in item["files"]:
            path = Path(file["path"])
            if path.exists():
                move_to_trash(path)
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
    return [Path(line) for line in out.splitlines() if line and Path(line).name == name][:50]


def find_moved(
    original: Path,
    size: int | None,
    duration: float | None,
    by_size: dict[int, list[Path]],
    exclude: set[str] | None = None,
) -> Path | None:
    """A candidate must match the recorded size exactly *and* the duration, so a different file
    that happens to share a name (or a size) is never mistaken for the one that moved."""
    if not size:
        return None
    candidates = list(by_size.get(size, []))
    candidates += [p for p in _spotlight(original.name) if p not in candidates]
    for candidate in candidates:
        if exclude and str(candidate) in exclude:
            continue
        try:
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
