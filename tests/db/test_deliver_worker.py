"""Tests for deliver worker with real Postgres + mocked S3/email."""

import uuid
from unittest.mock import patch, MagicMock

from video_to_essay import db
from video_to_essay.deliver_worker import _deliver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def make_user() -> str:
    return db.create_user(f"u{_uniq()}@test.com", f"wos_{_uniq()}")


def make_channel() -> str:
    return db.create_channel(f"UC_{_uniq()}", "Test Channel")


def make_processed_video(channel_id: str | None = None, **kw) -> str:
    """Create a video and mark it downloaded + processed. Returns video id."""
    yt_id = f"yt_{_uniq()}"
    vid = db.create_video(
        yt_id, f"https://youtube.com/watch?v={yt_id}",
        channel_id=channel_id, video_title="Test Video", **kw,
    )
    db.mark_video_downloaded(vid)
    db.mark_video_processed(vid)
    return vid


# ---------------------------------------------------------------------------
# E1: Happy path — essay found, email sent, delivery marked sent
# ---------------------------------------------------------------------------


@patch("video_to_essay.deliver_worker.track")
@patch("video_to_essay.deliver_worker.send_essay")
@patch("video_to_essay.deliver_worker.download_file")
def test_deliver_happy_path(
    mock_download_file: MagicMock,
    mock_send: MagicMock,
    mock_track: MagicMock,
    pg_container,
):
    """Essay is fetched from S3, email sent, delivery marked as sent."""
    uid = make_user()
    cid = make_channel()
    vid = make_processed_video(channel_id=cid)
    did = db.create_delivery(vid, uid, "one_off")

    mock_download_file.return_value = b"# My Essay\n\nSome content."

    _deliver()

    mock_send.assert_called_once()
    mock_download_file.assert_called()

    # Delivery should no longer be pending
    pending = db.get_pending_deliveries()
    assert all(d["id"] != did for d in pending)


# ---------------------------------------------------------------------------
# E4: 429 retry succeeds on second attempt — delivery marked sent
# ---------------------------------------------------------------------------


@patch("video_to_essay.deliver_worker.track")
@patch("video_to_essay.deliver_worker.send_essay")
@patch("video_to_essay.deliver_worker.download_file")
@patch("video_to_essay.deliver_worker.time.sleep")
def test_deliver_retries_on_429(
    mock_sleep: MagicMock,
    mock_download_file: MagicMock,
    mock_send: MagicMock,
    mock_track: MagicMock,
    pg_container,
):
    """Rate-limited on first attempt, succeeds on second."""
    uid = make_user()
    cid = make_channel()
    vid = make_processed_video(channel_id=cid)
    did = db.create_delivery(vid, uid, "one_off")

    mock_download_file.return_value = b"# Essay\n\nContent."

    # First call raises 429, second succeeds
    mock_send.side_effect = [Exception("429 Too Many Requests"), None]

    _deliver()

    assert mock_send.call_count == 2
    mock_sleep.assert_called_once()  # backoff between retries

    # Delivery marked sent, not failed
    pending = db.get_pending_deliveries()
    assert all(d["id"] != did for d in pending)
