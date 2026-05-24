"""Tests for download worker with real Postgres + mocked yt-dlp/S3."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

from video_to_essay import db
from video_to_essay.download_worker import (
    _cookies_file_from_env,
    _download_one,
    _min_interval_from_env,
    _wait_for_download_slot,
)


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
@patch("video_to_essay.download_worker.sample_frames")
@patch("video_to_essay.download_worker.extract_audio")
@patch("video_to_essay.download_worker.fetch_video_metadata")
@patch("video_to_essay.download_worker.download_video")
def test_download_one_happy_path(
    mock_download: MagicMock,
    mock_metadata: MagicMock,
    mock_extract_audio: MagicMock,
    mock_sample_frames: MagicMock,
    mock_upload: MagicMock,
    monkeypatch,
    pg_container,
    tmp_path: Path,
):
    """Video is downloaded, metadata saved, uploaded to S3, and marked downloaded."""
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    video = make_video(video_title="My Video")

    mock_metadata.return_value = {"title": "My Video", "channel": "Test"}

    with patch("video_to_essay.download_worker.RUNS_DIR", tmp_path):
        run_dir = tmp_path / video["youtube_video_id"] / "00_download"

        def fake_download(video_id, output_dir, cookies_path=None):
            video_path = output_dir / "video.mp4"
            video_path.write_bytes(b"fake video data")
            return video_path

        def fake_extract_audio(video_path, output_dir):
            audio_path = output_dir / "audio.mp3"
            audio_path.write_bytes(b"fake audio")
            return audio_path

        def fake_sample_frames(video_path, output_dir, interval_seconds):
            frame_path = output_dir / "frame_0001.jpg"
            frame_path.write_bytes(b"fake frame")
            return [frame_path]

        mock_download.side_effect = fake_download
        mock_extract_audio.side_effect = fake_extract_audio
        mock_sample_frames.side_effect = fake_sample_frames

        _download_one(video)

    # download_video called with the youtube video id
    mock_download.assert_called_once()
    assert mock_download.call_args[0][0] == video["youtube_video_id"]
    assert mock_download.call_args[0][2] is None
    mock_extract_audio.assert_called_once_with(run_dir / "video.mp4", run_dir)
    mock_sample_frames.assert_called_once_with(run_dir / "video.mp4", run_dir / "raw_frames", 5)

    # S3 upload called
    mock_upload.assert_called_once_with(
        video["youtube_video_id"],
        step_dirs=["00_download"],
        exclude_globs=["00_download/video.*"],
    )

    # Video marked as downloaded in db
    updated = db.get_video(video["id"])
    assert updated["downloaded_at"] is not None
    assert updated["video_title"] == "My Video"

    # Metadata file written
    meta_path = tmp_path / video["youtube_video_id"] / "00_download" / "metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["title"] == "My Video"
    assert (tmp_path / video["youtube_video_id"] / "00_download" / "audio.mp3").exists()
    assert (tmp_path / video["youtube_video_id"] / "00_download" / "raw_frames" / "frame_0001.jpg").exists()


def test_cookies_file_from_env_validates_file(monkeypatch, tmp_path: Path):
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(cookies_file))

    assert _cookies_file_from_env() == str(cookies_file)


def test_cookies_file_from_env_rejects_missing_file(monkeypatch, tmp_path: Path):
    missing = tmp_path / "missing-cookies.txt"
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(missing))

    try:
        _cookies_file_from_env()
    except FileNotFoundError as exc:
        assert "YTDLP_COOKIES_FILE" in str(exc)
        assert str(missing) in str(exc)
    else:
        raise AssertionError("missing cookies file should raise FileNotFoundError")


def test_min_interval_from_env_defaults_to_30_seconds(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_WORKER_MIN_INTERVAL_SECONDS", raising=False)

    assert _min_interval_from_env() == 30.0


def test_min_interval_from_env_parses_non_negative_seconds(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_WORKER_MIN_INTERVAL_SECONDS", "12.5")

    assert _min_interval_from_env() == 12.5


def test_min_interval_from_env_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_WORKER_MIN_INTERVAL_SECONDS", "-1")

    try:
        _min_interval_from_env()
    except ValueError as exc:
        assert "DOWNLOAD_WORKER_MIN_INTERVAL_SECONDS" in str(exc)
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative min interval should raise ValueError")


@patch("video_to_essay.download_worker.time.sleep")
@patch("video_to_essay.download_worker.time.monotonic")
def test_wait_for_download_slot_sleeps_remaining_interval(
    mock_monotonic: MagicMock,
    mock_sleep: MagicMock,
):
    mock_monotonic.side_effect = [100.0, 120.0]

    started_at = _wait_for_download_slot(last_attempt_at=80.0, min_interval_seconds=30.0)

    mock_sleep.assert_called_once_with(10.0)
    assert started_at == 120.0


@patch("video_to_essay.download_worker.time.sleep")
@patch("video_to_essay.download_worker.time.monotonic")
def test_wait_for_download_slot_does_not_sleep_when_interval_elapsed(
    mock_monotonic: MagicMock,
    mock_sleep: MagicMock,
):
    mock_monotonic.side_effect = [120.0, 120.0]

    started_at = _wait_for_download_slot(last_attempt_at=80.0, min_interval_seconds=30.0)

    mock_sleep.assert_not_called()
    assert started_at == 120.0


@patch("video_to_essay.download_worker.upload_run")
@patch("video_to_essay.download_worker.sample_frames")
@patch("video_to_essay.download_worker.extract_audio")
@patch("video_to_essay.download_worker.fetch_video_metadata")
@patch("video_to_essay.download_worker.download_video")
def test_download_one_passes_env_cookies_file_to_ytdlp(
    mock_download: MagicMock,
    mock_metadata: MagicMock,
    mock_extract_audio: MagicMock,
    mock_sample_frames: MagicMock,
    mock_upload: MagicMock,
    monkeypatch,
    pg_container,
    tmp_path: Path,
):
    video = make_video(video_title="Cookie Video")
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(cookies_file))
    mock_metadata.return_value = {"title": "Cookie Video", "channel": "Test"}

    def fake_download(video_id, output_dir, cookies_path=None):
        video_path = output_dir / "video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    def fake_extract_audio(video_path, output_dir):
        audio_path = output_dir / "audio.mp3"
        audio_path.write_bytes(b"fake audio")
        return audio_path

    def fake_sample_frames(video_path, output_dir, interval_seconds):
        frame_path = output_dir / "frame_0001.jpg"
        frame_path.write_bytes(b"fake frame")
        return [frame_path]

    mock_download.side_effect = fake_download
    mock_extract_audio.side_effect = fake_extract_audio
    mock_sample_frames.side_effect = fake_sample_frames

    with patch("video_to_essay.download_worker.RUNS_DIR", tmp_path):
        _download_one(video)

    mock_download.assert_called_once_with(
        video["youtube_video_id"],
        tmp_path / video["youtube_video_id"] / "00_download",
        str(cookies_file),
    )
    mock_metadata.assert_called_once_with(video["youtube_video_id"], str(cookies_file))
    mock_upload.assert_called_once()


# ---------------------------------------------------------------------------
# D5: Skips download when valid local file exists (has audio)
# ---------------------------------------------------------------------------


@patch("video_to_essay.download_worker.upload_run")
@patch("video_to_essay.download_worker.sample_frames")
@patch("video_to_essay.download_worker.extract_audio")
@patch("video_to_essay.download_worker.fetch_video_metadata")
@patch("video_to_essay.download_worker.download_video")
@patch("subprocess.run")
def test_download_one_skips_when_cached_with_audio(
    mock_ffprobe: MagicMock,
    mock_download: MagicMock,
    mock_metadata: MagicMock,
    mock_extract_audio: MagicMock,
    mock_sample_frames: MagicMock,
    mock_upload: MagicMock,
    monkeypatch,
    pg_container,
    tmp_path: Path,
):
    """When a valid video file already exists locally, download is skipped."""
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    video = make_video(video_title="Cached Video")

    # Pre-create a video file
    run_dir = tmp_path / video["youtube_video_id"] / "00_download"
    run_dir.mkdir(parents=True)
    (run_dir / "video.mp4").write_bytes(b"fake video data")

    # ffprobe reports an audio stream
    mock_ffprobe.return_value = MagicMock(stdout="audio\n")
    mock_metadata.return_value = {"title": "Cached Video"}

    def fake_extract_audio(video_path, output_dir):
        audio_path = output_dir / "audio.mp3"
        audio_path.write_bytes(b"fake audio")
        return audio_path

    def fake_sample_frames(video_path, output_dir, interval_seconds):
        frame_path = output_dir / "frame_0001.jpg"
        frame_path.write_bytes(b"fake frame")
        return [frame_path]

    mock_extract_audio.side_effect = fake_extract_audio
    mock_sample_frames.side_effect = fake_sample_frames

    with patch("video_to_essay.download_worker.RUNS_DIR", tmp_path):
        _download_one(video)

    # download_video should NOT have been called
    mock_download.assert_not_called()

    # But S3 upload and mark_downloaded still happen
    mock_upload.assert_called_once_with(
        video["youtube_video_id"],
        step_dirs=["00_download"],
        exclude_globs=["00_download/video.*"],
    )
    updated = db.get_video(video["id"])
    assert updated["downloaded_at"] is not None
