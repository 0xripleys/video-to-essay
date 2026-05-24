"""Tests 42-43: s3.py pure functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_to_essay.s3 import _content_type, _get_config, get_public_url, upload_run


# -- Test 42: get_public_url — correct URL format ----------------------------

def test_get_public_url(monkeypatch):
    _get_config.cache_clear()
    monkeypatch.setenv("S3_BUCKET_NAME", "my-bucket")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    try:
        url = get_public_url("runs/abc/essay.md")
        assert url == "https://my-bucket.s3.us-west-2.amazonaws.com/runs/abc/essay.md"
    finally:
        _get_config.cache_clear()


def test_get_public_url_default_region(monkeypatch):
    _get_config.cache_clear()
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.delenv("AWS_REGION", raising=False)
    try:
        url = get_public_url("key.txt")
        assert url == "https://test-bucket.s3.us-east-1.amazonaws.com/key.txt"
    finally:
        _get_config.cache_clear()


# -- Test 43: _content_type — MIME type mapping -------------------------------

@pytest.mark.parametrize(
    "path, expected",
    [
        (Path("image.jpg"), "image/jpeg"),
        (Path("data.json"), "application/json"),
        (Path("video.mp4"), "video/mp4"),
        (Path("file.xyz_unknown"), "application/octet-stream"),
    ],
)
def test_content_type(path: Path, expected: str):
    assert _content_type(path) == expected


def test_upload_run_excludes_matching_globs(tmp_path, monkeypatch):
    from video_to_essay import s3

    _get_config.cache_clear()
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(s3, "RUNS_DIR", tmp_path)

    dl_dir = tmp_path / "vid123" / "00_download"
    raw_dir = dl_dir / "raw_frames"
    raw_dir.mkdir(parents=True)
    (dl_dir / "metadata.json").write_text("{}")
    (dl_dir / "audio.mp3").write_bytes(b"audio")
    (dl_dir / "video.mp4").write_bytes(b"video")
    (raw_dir / "frame_0001.jpg").write_bytes(b"frame")

    client = MagicMock()
    with patch("video_to_essay.s3.get_s3_client", return_value=client):
        upload_run("vid123", step_dirs=["00_download"], exclude_globs=["00_download/video.*"])

    uploaded_keys = sorted(call.args[2] for call in client.upload_file.call_args_list)
    assert uploaded_keys == sorted([
        "runs/vid123/00_download/metadata.json",
        "runs/vid123/00_download/audio.mp3",
        "runs/vid123/00_download/raw_frames/frame_0001.jpg",
    ])
    assert "runs/vid123/00_download/video.mp4" not in uploaded_keys
    _get_config.cache_clear()
