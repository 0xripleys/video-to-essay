"""Postgres database for video-to-essay."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv()
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    workos_user_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    youtube_channel_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    thumbnail_url TEXT,
    description TEXT,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    youtube_video_id TEXT UNIQUE NOT NULL,
    youtube_url TEXT NOT NULL,
    video_title TEXT,
    channel_id TEXT REFERENCES channels(id),
    matched_playlist_ids TEXT[],
    downloaded_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    channel_id TEXT NOT NULL REFERENCES channels(id),
    playlist_ids TEXT[],
    poll_interval_hours INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    source TEXT NOT NULL CHECK(source IN ('one_off', 'subscription')),
    subscription_id TEXT REFERENCES subscriptions(id),
    sent_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(video_id, user_id)
);
"""


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return dsn


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(_dsn(), row_factory=dict_row)
    return conn


MIGRATIONS = [
    "ALTER TABLE channels ADD COLUMN IF NOT EXISTS thumbnail_url TEXT",
    "ALTER TABLE channels ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS playlist_ids TEXT[]",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS matched_playlist_ids TEXT[]",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS is_livestream BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS exclude_livestreams BOOLEAN NOT NULL DEFAULT FALSE",
]


def init_db() -> None:
    """Create tables if they don't exist."""
    with psycopg.connect(_dsn()) as conn:
        for statement in SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        for migration in MIGRATIONS:
            conn.execute(migration)
        conn.commit()


# --- Users ---


def create_user(email: str, workos_user_id: str) -> str:
    user_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, workos_user_id, created_at) VALUES (%s, %s, %s, %s)",
            (user_id, email, workos_user_id, _now()),
        )
        conn.commit()
    return user_id


def get_user_by_workos_id(workos_user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE workos_user_id = %s", (workos_user_id,)
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
            "INSERT INTO channels (id, youtube_channel_id, name, created_at) VALUES (%s, %s, %s, %s)",
            (channel_id, youtube_channel_id, name, _now()),
        )
        conn.commit()
    return channel_id


def get_channel_by_youtube_id(youtube_channel_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM channels WHERE youtube_channel_id = %s",
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
            "UPDATE channels SET last_checked_at = %s WHERE id = %s",
            (_now(), channel_id),
        )
        conn.commit()


def update_channel_name(channel_id: str, name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE channels SET name = %s WHERE id = %s",
            (name, channel_id),
        )
        conn.commit()


def get_channels_due_for_check() -> list[dict[str, Any]]:
    """Return channels where at least one active subscriber's poll interval has elapsed."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*, MIN(s.poll_interval_hours) as min_interval
            FROM channels c
            JOIN subscriptions s ON s.channel_id = c.id AND s.active = TRUE
            WHERE c.last_checked_at IS NULL
               OR c.last_checked_at + (
                   (SELECT MIN(s2.poll_interval_hours)
                    FROM subscriptions s2
                    WHERE s2.channel_id = c.id AND s2.active = TRUE
                   ) || ' hours')::interval <= NOW()
            GROUP BY c.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


# --- Subscriptions ---


def create_subscription(
    user_id: str,
    channel_id: str,
    poll_interval_hours: int = 1,
    playlist_ids: list[str] | None = None,
) -> str:
    sub_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO subscriptions (id, user_id, channel_id, playlist_ids, poll_interval_hours, active, created_at) VALUES (%s, %s, %s, %s, %s, TRUE, %s)",
            (sub_id, user_id, channel_id, playlist_ids, poll_interval_hours, _now()),
        )
        conn.commit()
    return sub_id


def list_user_subscriptions(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, c.youtube_channel_id, c.name as channel_name
            FROM subscriptions s
            JOIN channels c ON c.id = s.channel_id
            WHERE s.user_id = %s AND s.active = TRUE
            ORDER BY s.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_subscription(sub_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id = %s", (sub_id,)
        ).fetchone()
    return dict(row) if row else None


def get_channel_subscriptions(channel_id: str) -> list[dict[str, Any]]:
    """Return all active subscriptions for a channel."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE channel_id = %s AND active = TRUE",
            (channel_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def deactivate_subscription(sub_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE subscriptions SET active = FALSE WHERE id = %s", (sub_id,)
        )
        conn.commit()


def update_subscription_interval(sub_id: str, poll_interval_hours: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE subscriptions SET poll_interval_hours = %s WHERE id = %s",
            (poll_interval_hours, sub_id),
        )
        conn.commit()


# --- Videos ---


def create_video(
    youtube_video_id: str,
    youtube_url: str,
    channel_id: str | None = None,
    video_title: str | None = None,
    matched_playlist_ids: list[str] | None = None,
    is_livestream: bool = False,
) -> str:
    video_id = _uid()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, youtube_video_id, youtube_url, video_title, channel_id, matched_playlist_ids, is_livestream, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (video_id, youtube_video_id, youtube_url, video_title, channel_id, matched_playlist_ids, is_livestream, _now()),
        )
        conn.commit()
    return video_id


def get_video(video_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = %s", (video_id,)
        ).fetchone()
    return dict(row) if row else None


def get_video_by_youtube_id(youtube_video_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE youtube_video_id = %s", (youtube_video_id,)
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
            SELECT DISTINCT ON (v.id) v.*, c.name as channel_name,
                   d.source, d.sent_at as delivery_sent_at
            FROM videos v
            LEFT JOIN channels c ON c.id = v.channel_id
            LEFT JOIN deliveries d ON d.video_id = v.id AND d.user_id = %s
            WHERE d.user_id = %s
               OR v.channel_id IN (
                   SELECT s.channel_id FROM subscriptions s
                   WHERE s.user_id = %s AND s.active = TRUE
               )
            ORDER BY v.id, v.created_at DESC
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
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [video_id]
    with _connect() as conn:
        conn.execute(f"UPDATE videos SET {set_clause} WHERE id = %s", values)
        conn.commit()


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
                "INSERT INTO deliveries (id, video_id, user_id, source, subscription_id, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (delivery_id, video_id, user_id, source, subscription_id, _now()),
            )
            conn.commit()
        return delivery_id
    except psycopg.errors.UniqueViolation:
        return None


def create_subscription_deliveries() -> int:
    """Create delivery rows for processed subscription videos that haven't been delivered yet.

    Returns the number of rows created.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO deliveries (id, video_id, user_id, source, subscription_id, created_at)
            SELECT gen_random_uuid()::text, v.id, u.id, 'subscription', s.id, NOW()
            FROM videos v
            JOIN channels c ON c.id = v.channel_id
            JOIN subscriptions s ON s.channel_id = c.id AND s.active = TRUE
            JOIN users u ON u.id = s.user_id
            LEFT JOIN deliveries d ON d.video_id = v.id AND d.user_id = u.id
            WHERE v.processed_at IS NOT NULL
              AND d.id IS NULL
              AND (s.playlist_ids IS NULL OR v.matched_playlist_ids && s.playlist_ids)
              AND (s.exclude_livestreams = FALSE OR v.is_livestream = FALSE)
            ON CONFLICT DO NOTHING
            """
        )
        conn.commit()
        return cur.rowcount


def get_pending_deliveries() -> list[dict[str, Any]]:
    """Deliveries where the video is processed but email not yet sent."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, v.youtube_video_id, v.video_title, u.email,
                   c.name as channel_name
            FROM deliveries d
            JOIN videos v ON v.id = d.video_id
            JOIN users u ON u.id = d.user_id
            LEFT JOIN channels c ON c.id = v.channel_id
            WHERE d.sent_at IS NULL
              AND d.error IS NULL
              AND v.processed_at IS NOT NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]



def mark_delivery_sent(delivery_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE deliveries SET sent_at = %s WHERE id = %s",
            (_now(), delivery_id),
        )
        conn.commit()


def mark_delivery_failed(delivery_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE deliveries SET error = %s WHERE id = %s",
            (error, delivery_id),
        )
        conn.commit()
