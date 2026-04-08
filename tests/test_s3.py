"""Tests 42-43: s3.py pure functions."""

from pathlib import Path

import pytest

from video_to_essay.s3 import _content_type, _get_config, get_public_url


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
