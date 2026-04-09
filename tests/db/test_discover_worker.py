"""Tests 70-72: discover worker with real Postgres + mocked YouTube API."""

import uuid
from datetime import datetime, timezone, timedelta

import httpx
import respx

from video_to_essay import db
from video_to_essay.discover_worker import _check_channel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

API_KEY = "fake-api-key"


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def make_user() -> str:
    return db.create_user(f"u{_uniq()}@test.com", f"wos_{_uniq()}")


def make_channel(youtube_channel_id: str | None = None, name: str | None = None) -> dict:
    """Create a channel and return the full channel dict."""
    yt_id = youtube_channel_id or f"UC{_uniq()}"
    ch_name = name or yt_id
    db.create_channel(yt_id, ch_name)
    return db.get_channel_by_youtube_id(yt_id)


def mock_uploads(
    router: respx.MockRouter,
    channel: dict,
    videos: list[tuple[str, str, datetime]],
    channel_title: str = "Test Channel",
) -> None:
    """Mock the playlistItems call for a channel's uploads playlist."""
    uploads_id = "UU" + channel["youtube_channel_id"][2:]
    items = [
        {
            "snippet": {
                "resourceId": {"videoId": vid},
                "title": title,
                "publishedAt": pub.isoformat(),
                "channelTitle": channel_title,
            }
        }
        for vid, title, pub in videos
    ]
    router.get(PLAYLIST_ITEMS_URL, params__contains={"playlistId": uploads_id}).mock(
        return_value=httpx.Response(200, json={"items": items}),
    )


def mock_classify(
    router: respx.MockRouter,
    videos: list[tuple[str, str, dict | None]],
) -> None:
    """Mock the videos endpoint used for classification (shorts/livestream detection)."""
    items = []
    for vid, duration, live_details in videos:
        item: dict = {
            "id": vid,
            "contentDetails": {"duration": duration},
        }
        if live_details is not None:
            item["liveStreamingDetails"] = live_details
        items.append(item)
    router.get(VIDEOS_URL).mock(
        return_value=httpx.Response(200, json={"items": items}),
    )


def set_last_checked(raw_conn, channel: dict, when: datetime) -> dict:
    """Set last_checked_at on a channel and return the refreshed dict."""
    raw_conn.execute(
        "UPDATE channels SET last_checked_at = %s WHERE id = %s",
        (when, channel["id"]),
    )
    raw_conn.commit()
    return db.get_channel_by_youtube_id(channel["youtube_channel_id"])


# ---------------------------------------------------------------------------
# M1: _check_channel inserts new videos into db
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_inserts_new_videos(raw_conn):
    """Two new videos after cutoff are inserted into the database."""
    now = datetime.now(timezone.utc)
    channel = make_channel()
    user_id = make_user()
    db.create_subscription(user_id, channel["id"])

    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=1))

    vid_1, vid_2 = f"vid_{_uniq()}", f"vid_{_uniq()}"
    published = now - timedelta(minutes=30)

    mock_uploads(respx, channel, [
        (vid_1, "Video One", published),
        (vid_2, "Video Two", published - timedelta(minutes=1)),
    ])
    mock_classify(respx, [
        (vid_1, "PT10M0S", None),
        (vid_2, "PT10M0S", None),
    ])

    count = _check_channel(channel, API_KEY)

    assert count == 2

    v1 = db.get_video_by_youtube_id(vid_1)
    assert v1 is not None
    assert v1["video_title"] == "Video One"
    assert v1["channel_id"] == channel["id"]
    assert v1["youtube_url"] == f"https://www.youtube.com/watch?v={vid_1}"

    v2 = db.get_video_by_youtube_id(vid_2)
    assert v2 is not None
    assert v2["video_title"] == "Video Two"


# ---------------------------------------------------------------------------
# M2: Skips videos that already exist in db
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_skips_existing_videos(raw_conn):
    """Pre-existing video is not re-inserted; only the new one is added."""
    now = datetime.now(timezone.utc)
    channel = make_channel()
    user_id = make_user()
    db.create_subscription(user_id, channel["id"])
    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=1))

    vid_existing = f"vid_{_uniq()}"
    vid_new = f"vid_{_uniq()}"

    # Pre-insert vid_existing
    existing_id = db.create_video(
        vid_existing, f"https://www.youtube.com/watch?v={vid_existing}",
        channel_id=channel["id"], video_title="Already There",
    )

    published = now - timedelta(minutes=30)
    mock_uploads(respx, channel, [
        (vid_existing, "Already There", published),
        (vid_new, "Brand New", published - timedelta(minutes=1)),
    ])
    mock_classify(respx, [
        (vid_new, "PT10M0S", None),
    ])

    count = _check_channel(channel, API_KEY)

    assert count == 1

    # Existing video row unchanged (same internal ID)
    v = db.get_video_by_youtube_id(vid_existing)
    assert v["id"] == existing_id

    # New video inserted
    assert db.get_video_by_youtube_id(vid_new) is not None


# ---------------------------------------------------------------------------
# M3: Respects cutoff date — stops at videos older than last_checked_at
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_respects_cutoff(raw_conn):
    """Only videos published after last_checked_at are inserted."""
    now = datetime.now(timezone.utc)
    channel = make_channel()
    user_id = make_user()
    db.create_subscription(user_id, channel["id"])
    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=2))

    vid_recent = f"vid_{_uniq()}"
    vid_old_1 = f"vid_{_uniq()}"
    vid_old_2 = f"vid_{_uniq()}"

    # YouTube returns reverse-chronological order
    mock_uploads(respx, channel, [
        (vid_recent, "Recent", now - timedelta(hours=1)),
        (vid_old_1, "Old One", now - timedelta(hours=3)),
        (vid_old_2, "Old Two", now - timedelta(hours=4)),
    ])
    mock_classify(respx, [
        (vid_recent, "PT10M0S", None),
    ])

    count = _check_channel(channel, API_KEY)

    assert count == 1
    assert db.get_video_by_youtube_id(vid_recent) is not None
    assert db.get_video_by_youtube_id(vid_old_1) is None
    assert db.get_video_by_youtube_id(vid_old_2) is None


# ---------------------------------------------------------------------------
# M4: Updates last_checked_at after run
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_updates_last_checked_at(raw_conn):
    """last_checked_at is updated even when there are no new videos."""
    now = datetime.now(timezone.utc)
    old_checked = now - timedelta(hours=1)
    channel = make_channel()
    user_id = make_user()
    db.create_subscription(user_id, channel["id"])
    channel = set_last_checked(raw_conn, channel, old_checked)

    # Empty uploads
    mock_uploads(respx, channel, [])

    _check_channel(channel, API_KEY)

    updated = db.get_channel_by_youtube_id(channel["youtube_channel_id"])
    assert updated["last_checked_at"] > old_checked


# ---------------------------------------------------------------------------
# M5: Skips videos matching no subscriber playlists
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_skips_unmatched_playlist(raw_conn):
    """When all subscribers filter by playlist, skip videos not in any playlist."""
    now = datetime.now(timezone.utc)
    channel = make_channel()
    user_id = make_user()
    db.create_subscription(user_id, channel["id"], playlist_ids=["PLfiltered"])
    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=1))

    vid = f"vid_{_uniq()}"
    published = now - timedelta(minutes=30)

    mock_uploads(respx, channel, [
        (vid, "Filtered Out", published),
    ])

    # Mock the playlist membership check — video is NOT in PLfiltered
    respx.get(
        PLAYLIST_ITEMS_URL, params__contains={"playlistId": "PLfiltered"}
    ).mock(
        return_value=httpx.Response(200, json={"items": []}),
    )

    count = _check_channel(channel, API_KEY)

    assert count == 0
    assert db.get_video_by_youtube_id(vid) is None


# ---------------------------------------------------------------------------
# M6: Inserts without playlist check when any subscriber is unfiltered
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_skips_playlist_check_when_unfiltered(raw_conn):
    """When any subscriber has no playlist filter, skip playlist membership check entirely."""
    now = datetime.now(timezone.utc)
    channel = make_channel()

    # Two subscribers: one unfiltered, one filtered
    user_1 = make_user()
    db.create_subscription(user_1, channel["id"])  # playlist_ids=None (unfiltered)
    user_2 = make_user()
    db.create_subscription(user_2, channel["id"], playlist_ids=["PLfoo"])

    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=1))

    vid = f"vid_{_uniq()}"
    published = now - timedelta(minutes=30)

    mock_uploads(respx, channel, [
        (vid, "Should Insert", published),
    ])
    mock_classify(respx, [
        (vid, "PT10M0S", None),
    ])

    # Do NOT mock PLfoo — if it's called, respx will raise an error

    count = _check_channel(channel, API_KEY)

    assert count == 1
    assert db.get_video_by_youtube_id(vid) is not None


# ---------------------------------------------------------------------------
# M7: Updates channel name from API when name is placeholder
# ---------------------------------------------------------------------------


@respx.mock
def test_check_channel_updates_placeholder_name(raw_conn):
    """Channel name is updated from API response when it matches the channel ID (placeholder)."""
    now = datetime.now(timezone.utc)
    yt_id = f"UC{_uniq()}"
    channel = make_channel(youtube_channel_id=yt_id, name=yt_id)  # name == id → placeholder
    user_id = make_user()
    db.create_subscription(user_id, channel["id"])
    channel = set_last_checked(raw_conn, channel, now - timedelta(hours=1))

    vid = f"vid_{_uniq()}"
    published = now - timedelta(minutes=30)

    mock_uploads(respx, channel, [
        (vid, "A Video", published),
    ], channel_title="Cool Channel Name")
    mock_classify(respx, [
        (vid, "PT10M0S", None),
    ])

    _check_channel(channel, API_KEY)

    updated = db.get_channel_by_youtube_id(yt_id)
    assert updated["name"] == "Cool Channel Name"
