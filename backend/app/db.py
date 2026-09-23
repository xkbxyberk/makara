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
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
"""

JSON_COLUMNS = ("request", "output_files")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.data_dir() / "videodownloader.sqlite3", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
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
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT ?", [limit]
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
