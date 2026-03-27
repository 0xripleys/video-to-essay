"""SQLite database for video-to-essay."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path("data/surat.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    workos_user_id TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    youtube_channel_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    last_checked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    youtube_video_id TEXT UNIQUE NOT NULL,
    youtube_url TEXT NOT NULL,
    video_title TEXT,
    channel_id TEXT REFERENCES channels(id),
    downloaded_at TEXT,
    processed_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    channel_id TEXT NOT NULL REFERENCES channels(id),
    poll_interval_hours INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    source TEXT NOT NULL CHECK(source IN ('one_off', 'subscription')),
    subscription_id TEXT REFERENCES subscriptions(id),
    sent_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(video_id, user_id)
);
"""


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for statement in SCHEMA.strip().split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)
    return conn


# --- Users ---


def create_user(email: str, workos_user_id: str) -> str:
    user_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, workos_user_id, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, workos_user_id, _now()),
        )
    return user_id


def get_user_by_workos_id(workos_user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE workos_user_id = ?", (workos_user_id,)
        ).fetchone()
    return dict(row) if row else None


def upsert_user(email: str, workos_user_id: str) -> dict[str, Any]:
    """Create user if not exists, return user dict."""
    user = get_user_by_workos_id(workos_user_id)
    if user:
        return user
    user_id = create_user(email, workos_user_id)
    return {"id": user_id, "email": email, "workos_user_id": workos_user_id}


# --- Channels ---


def create_channel(youtube_channel_id: str, name: str) -> str:
    channel_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO channels (id, youtube_channel_id, name, created_at) VALUES (?, ?, ?, ?)",
            (channel_id, youtube_channel_id, name, _now()),
        )
    return channel_id


def get_channel_by_youtube_id(youtube_channel_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM channels WHERE youtube_channel_id = ?",
            (youtube_channel_id,),
        ).fetchone()
    return dict(row) if row else None


def get_or_create_channel(youtube_channel_id: str, name: str) -> dict[str, Any]:
    channel = get_channel_by_youtube_id(youtube_channel_id)
    if channel:
        return channel
    channel_id = create_channel(youtube_channel_id, name)
    return {
        "id": channel_id,
        "youtube_channel_id": youtube_channel_id,
        "name": name,
    }


def update_channel_checked(channel_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE channels SET last_checked_at = ? WHERE id = ?",
            (_now(), channel_id),
        )


def get_channels_due_for_check() -> list[dict[str, Any]]:
    """Return channels where at least one active subscriber's poll interval has elapsed."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*, MIN(s.poll_interval_hours) as min_interval
            FROM channels c
            JOIN subscriptions s ON s.channel_id = c.id AND s.active = 1
            WHERE c.last_checked_at IS NULL
               OR datetime(c.last_checked_at, '+' || (
                   SELECT MIN(s2.poll_interval_hours)
                   FROM subscriptions s2
                   WHERE s2.channel_id = c.id AND s2.active = 1
               ) || ' hours') <= datetime('now')
            GROUP BY c.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


# --- Subscriptions ---


def create_subscription(
    user_id: str, channel_id: str, poll_interval_hours: int = 1
) -> str:
    sub_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO subscriptions (id, user_id, channel_id, poll_interval_hours, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (sub_id, user_id, channel_id, poll_interval_hours, _now()),
        )
    return sub_id


def list_user_subscriptions(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, c.youtube_channel_id, c.name as channel_name
            FROM subscriptions s
            JOIN channels c ON c.id = s.channel_id
            WHERE s.user_id = ? AND s.active = 1
            ORDER BY s.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_subscription(sub_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
        ).fetchone()
    return dict(row) if row else None


def deactivate_subscription(sub_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE id = ?", (sub_id,)
        )


def update_subscription_interval(sub_id: str, poll_interval_hours: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE subscriptions SET poll_interval_hours = ? WHERE id = ?",
            (poll_interval_hours, sub_id),
        )


# --- Videos ---


def create_video(
    youtube_video_id: str,
    youtube_url: str,
    channel_id: str | None = None,
    video_title: str | None = None,
) -> str:
    video_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, youtube_video_id, youtube_url, video_title, channel_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, youtube_video_id, youtube_url, video_title, channel_id, _now()),
        )
    return video_id


def get_video(video_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
    return dict(row) if row else None


def get_video_by_youtube_id(youtube_video_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE youtube_video_id = ?", (youtube_video_id,)
        ).fetchone()
    return dict(row) if row else None


def get_or_create_video(
    youtube_video_id: str,
    youtube_url: str,
    channel_id: str | None = None,
    video_title: str | None = None,
) -> dict[str, Any]:
    video = get_video_by_youtube_id(youtube_video_id)
    if video:
        return video
    vid = create_video(youtube_video_id, youtube_url, channel_id, video_title)
    return {
        "id": vid,
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
        "video_title": video_title,
        "channel_id": channel_id,
    }


def list_user_videos(user_id: str) -> list[dict[str, Any]]:
    """List all videos for a user: one-offs (via deliveries) + subscription videos."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT v.*, c.name as channel_name,
                   d.source, d.sent_at as delivery_sent_at
            FROM videos v
            LEFT JOIN channels c ON c.id = v.channel_id
            LEFT JOIN deliveries d ON d.video_id = v.id AND d.user_id = ?
            WHERE d.user_id = ?
               OR v.channel_id IN (
                   SELECT s.channel_id FROM subscriptions s
                   WHERE s.user_id = ? AND s.active = 1
               )
            ORDER BY v.created_at DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def get_videos_pending_download() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE downloaded_at IS NULL AND error IS NULL ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_videos_pending_processing() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE downloaded_at IS NOT NULL AND processed_at IS NULL AND error IS NULL ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_video_downloaded(video_id: str, video_title: str | None = None) -> None:
    fields: dict[str, Any] = {"downloaded_at": _now()}
    if video_title:
        fields["video_title"] = video_title
    _update_video(video_id, **fields)


def mark_video_processed(video_id: str) -> None:
    _update_video(video_id, processed_at=_now())


def mark_video_failed(video_id: str, error: str) -> None:
    _update_video(video_id, error=error)


def _update_video(video_id: str, **fields: Any) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [video_id]
    with _connect() as conn:
        conn.execute(f"UPDATE videos SET {set_clause} WHERE id = ?", values)


# --- Deliveries ---


def create_delivery(
    video_id: str,
    user_id: str,
    source: str,
    subscription_id: str | None = None,
) -> str | None:
    """Create a delivery record. Returns delivery id, or None if duplicate."""
    delivery_id = _uid()
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO deliveries (id, video_id, user_id, source, subscription_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (delivery_id, video_id, user_id, source, subscription_id, _now()),
            )
        return delivery_id
    except sqlite3.IntegrityError:
        return None


def get_pending_one_off_deliveries() -> list[dict[str, Any]]:
    """One-off deliveries where the video is processed but email not yet sent."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, v.youtube_video_id, v.video_title, u.email
            FROM deliveries d
            JOIN videos v ON v.id = d.video_id
            JOIN users u ON u.id = d.user_id
            WHERE d.source = 'one_off'
              AND d.sent_at IS NULL
              AND d.error IS NULL
              AND v.processed_at IS NOT NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_pending_subscription_deliveries() -> list[dict[str, Any]]:
    """Subscription videos that are processed but not yet delivered to subscribers."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT v.id as video_id, v.youtube_video_id, v.video_title,
                   u.id as user_id, u.email, s.id as subscription_id
            FROM videos v
            JOIN channels c ON c.id = v.channel_id
            JOIN subscriptions s ON s.channel_id = c.id AND s.active = 1
            JOIN users u ON u.id = s.user_id
            LEFT JOIN deliveries d ON d.video_id = v.id AND d.user_id = u.id
            WHERE v.processed_at IS NOT NULL
              AND d.id IS NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def mark_delivery_sent(delivery_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE deliveries SET sent_at = ? WHERE id = ?",
            (_now(), delivery_id),
        )


def mark_delivery_failed(delivery_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE deliveries SET error = ? WHERE id = ?",
            (error, delivery_id),
        )
