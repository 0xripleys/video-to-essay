"""SQLite database for job tracking."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path("data/jobs.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    youtube_url TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    current_step TEXT,
    error TEXT,
    video_title TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA)
    return conn


def create_job(youtube_url: str, email: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, youtube_url, email, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (job_id, youtube_url, email, now),
        )
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def claim_pending_job() -> dict[str, Any] | None:
    """Atomically claim the oldest pending job for processing."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE jobs SET status = 'processing' WHERE id = ? AND status = 'pending'",
            (row["id"],),
        )
    return dict(row)


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)


def complete_job(job_id: str, video_title: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    fields: dict[str, Any] = {"status": "completed", "completed_at": now}
    if video_title:
        fields["video_title"] = video_title
    update_job(job_id, **fields)


def fail_job(job_id: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    update_job(job_id, status="failed", error=error, completed_at=now)
