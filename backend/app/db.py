"""SQLite storage. Plain sqlite3: one small schema does not earn an ORM."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from app import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    status        TEXT NOT NULL,
    stage         TEXT NOT NULL,
    title         TEXT,
    source_url    TEXT,
    mode          TEXT,
    request       TEXT NOT NULL,
    progress      REAL NOT NULL DEFAULT 0,
    speed         REAL,
    eta           REAL,
    item_index    INTEGER,
    item_count    INTEGER,
    output_files  TEXT NOT NULL DEFAULT '[]',
    error_code    TEXT,
    error_raw     TEXT,
    warnings      TEXT NOT NULL DEFAULT '[]',
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    attempts      INTEGER NOT NULL DEFAULT 0,  -- automatic retries so far (P6d)
    retry_at      REAL,                        -- a waiting retry starts then, not before
    pieces        TEXT,                        -- the segment map: a digit 0-9 per cell
    connections   INTEGER,
    fragments     TEXT                         -- [done, total] for HLS/DASH
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
"""

JSON_COLUMNS = ("request", "output_files", "warnings", "fragments")
# Columns added after the first release, applied to existing databases on start-up.
MIGRATIONS = {
    "warnings": "ALTER TABLE jobs ADD COLUMN warnings TEXT NOT NULL DEFAULT '[]'",
    "attempts": "ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
    "retry_at": "ALTER TABLE jobs ADD COLUMN retry_at REAL",
    "pieces": "ALTER TABLE jobs ADD COLUMN pieces TEXT",
    "connections": "ALTER TABLE jobs ADD COLUMN connections INTEGER",
    "fragments": "ALTER TABLE jobs ADD COLUMN fragments TEXT",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.data_dir() / "videodownloader.sqlite3", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, statement in MIGRATIONS.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()
    return conn


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for column in JSON_COLUMNS:
        out[column] = json.loads(out[column]) if out[column] else None
    return out


class JobStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(self, job: dict[str, Any]) -> dict[str, Any]:
        job = {"created_at": time.time(), **job}
        columns = list(job)
        values = [json.dumps(job[c]) if c in JSON_COLUMNS else job[c] for c in columns]
        self.conn.execute(
            f"INSERT INTO jobs ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        self.conn.commit()
        return self.get(job["id"])  # type: ignore[return-value]

    def update(self, job_id: str, **changes: Any) -> dict[str, Any] | None:
        if changes:
            assignments = ", ".join(f"{column} = ?" for column in changes)
            values = [json.dumps(v) if c in JSON_COLUMNS else v for c, v in changes.items()]
            self.conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", [*values, job_id])
            self.conn.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return _row(self.conn.execute("SELECT * FROM jobs WHERE id = ?", [job_id]).fetchone())

    def all(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [r for r in (_row(row) for row in rows) if r is not None]

    def next_queued(self, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' AND (retry_at IS NULL OR retry_at <= ?) "
            "ORDER BY created_at LIMIT ?",
            [time.time(), limit],
        ).fetchall()
        return [r for r in (_row(row) for row in rows) if r is not None]

    def delete(self, job_id: str) -> None:
        self.conn.execute("DELETE FROM jobs WHERE id = ?", [job_id])
        self.conn.commit()

    def requeue_interrupted(self) -> int:
        """Jobs that were running when the server died go back to the queue and resume."""
        cursor = self.conn.execute(
            "UPDATE jobs SET status = 'queued', stage = 'queued', speed = NULL, eta = NULL "
            "WHERE status = 'running'"
        )
        self.conn.commit()
        return cursor.rowcount
