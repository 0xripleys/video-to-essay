"""Tests for download worker with real Postgres + mocked yt-dlp/S3."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

from video_to_essay import db
from video_to_essay.download_worker import _download_one


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def make_user() -> str:
    return db.create_user(f"u{_uniq()}@test.com", f"wos_{_uniq()}")


def make_channel() -> str:
    return db.create_channel(f"UC_{_uniq()}", "Test Channel")


def make_video(channel_id: str | None = None, **kw) -> dict:
    yt_id = f"yt_{_uniq()}"
    vid = db.create_video(
        yt_id, f"https://youtube.com/watch?v={yt_id}",
        channel_id=channel_id, **kw,
    )
    return db.get_video(vid)


# ---------------------------------------------------------------------------
# D1: Happy path — downloads, uploads to S3, marks downloaded with title
# ---------------------------------------------------------------------------


@patch("video_to_essay.download_worker.upload_run")
@patch("video_to_essay.download_worker.fetch_video_metadata")
@patch("video_to_essay.download_worker.download_video")
def test_download_one_happy_path(
    mock_download: MagicMock,
    mock_metadata: MagicMock,
    mock_upload: MagicMock,
    pg_container,
    tmp_path: Path,
):
    """Video is downloaded, metadata saved, uploaded to S3, and marked downloaded."""
    video = make_video(video_title="My Video")

    mock_metadata.return_value = {"title": "My Video", "channel": "Test"}

    with patch("video_to_essay.download_worker.RUNS_DIR", tmp_path):
        _download_one(video)

    # download_video called with the youtube video id
    mock_download.assert_called_once()
    assert mock_download.call_args[0][0] == video["youtube_video_id"]

    # S3 upload called
    mock_upload.assert_called_once_with(video["youtube_video_id"], step_dirs=["00_download"])

    # Video marked as downloaded in db
    updated = db.get_video(video["id"])
    assert updated["downloaded_at"] is not None
    assert updated["video_title"] == "My Video"

    # Metadata file written
    meta_path = tmp_path / video["youtube_video_id"] / "00_download" / "metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["title"] == "My Video"


# ---------------------------------------------------------------------------
# D5: Skips download when valid local file exists (has audio)
# ---------------------------------------------------------------------------


@patch("video_to_essay.download_worker.upload_run")
@patch("video_to_essay.download_worker.fetch_video_metadata")
@patch("video_to_essay.download_worker.download_video")
@patch("subprocess.run")
def test_download_one_skips_when_cached_with_audio(
    mock_ffprobe: MagicMock,
    mock_download: MagicMock,
    mock_metadata: MagicMock,
    mock_upload: MagicMock,
    pg_container,
    tmp_path: Path,
):
    """When a valid video file already exists locally, download is skipped."""
    video = make_video(video_title="Cached Video")

    # Pre-create a video file
    run_dir = tmp_path / video["youtube_video_id"] / "00_download"
    run_dir.mkdir(parents=True)
    (run_dir / "video.mp4").write_bytes(b"fake video data")

    # ffprobe reports an audio stream
    mock_ffprobe.return_value = MagicMock(stdout="audio\n")
    mock_metadata.return_value = {"title": "Cached Video"}

    with patch("video_to_essay.download_worker.RUNS_DIR", tmp_path):
        _download_one(video)

    # download_video should NOT have been called
    mock_download.assert_not_called()

    # But S3 upload and mark_downloaded still happen
    mock_upload.assert_called_once()
    updated = db.get_video(video["id"])
    assert updated["downloaded_at"] is not None
