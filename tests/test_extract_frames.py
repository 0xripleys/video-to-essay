"""Tests 12-21: extract_frames.py pure functions."""

import base64
from pathlib import Path
from unittest.mock import patch

import imagehash
import pytest
from PIL import Image

from video_to_essay.extract_frames import (
    _in_sponsor_range,
    dedup_frames,
    encode_image_base64,
    frame_seconds,
    frame_timestamp,
    get_transcript_context,
    parse_transcript,
)


# -- Test 12: parse_transcript — single-speaker format -----------------------

def test_parse_transcript_single_speaker():
    transcript = "[00:00] Hello everyone.\n[01:30] Let's begin."
    result = parse_transcript(transcript)
    assert result == [(0, "Hello everyone."), (90, "Let's begin.")]


# -- Test 13: parse_transcript — multi-speaker format ------------------------

def test_parse_transcript_multi_speaker():
    transcript = (
        "**Alice** [00:30]\n"
        "Hello there\n"
        "\n"
        "**Bob** [01:00]\n"
        "Hi back"
    )
    result = parse_transcript(transcript)
    assert result == [(30, "Hello there"), (60, "Hi back")]


# -- Test 14: parse_transcript — empty/malformed input -----------------------

@pytest.mark.parametrize("transcript", ["", "random text", "no timestamps here"])
def test_parse_transcript_empty(transcript: str):
    assert parse_transcript(transcript) == []


# -- Test 15: get_transcript_context — within window -------------------------

def test_get_transcript_context_within_window():
    entries = [(0, "A"), (10, "B"), (30, "C"), (60, "D")]
    result = get_transcript_context(12, entries, window=15)
    assert "A" in result
    assert "B" in result
    assert "C" not in result
    assert "D" not in result


# -- Test 16: get_transcript_context — empty when no entries in window --------

def test_get_transcript_context_empty():
    entries = [(0, "A"), (10, "B"), (30, "C")]
    result = get_transcript_context(100, entries, window=15)
    assert result == ""


# -- Test 17: frame_seconds — frame number to seconds ------------------------

@pytest.mark.parametrize(
    "filename, interval, expected",
    [
        ("frame_0001.jpg", 5, 0),
        ("frame_0003.jpg", 5, 10),
        ("frame_0010.jpg", 10, 90),
    ],
)
def test_frame_seconds(filename: str, interval: int, expected: int):
    assert frame_seconds(Path(filename), interval) == expected


# -- Test 18: frame_timestamp — MM:SS formatting -----------------------------

@pytest.mark.parametrize(
    "filename, interval, expected",
    [
        ("frame_0001.jpg", 5, "00:00"),
        ("frame_0013.jpg", 5, "01:00"),
        ("frame_0025.jpg", 10, "04:00"),
    ],
)
def test_frame_timestamp(filename: str, interval: int, expected: str):
    assert frame_timestamp(Path(filename), interval) == expected


# -- Test 19: _in_sponsor_range — inside/outside/padding ----------------------

@pytest.mark.parametrize(
    "seconds, expected",
    [
        (150, True),   # inside range
        (50, False),   # outside range
        (96, True),    # within padding (100-5=95 <= 96)
        (94, False),   # outside padding (95 > 94)
        (204, True),   # within end padding (204 <= 200+5)
        (206, False),  # outside end padding (206 > 205)
    ],
)
def test_in_sponsor_range(seconds: int, expected: bool):
    assert _in_sponsor_range(seconds, [(100, 200)], padding=5) == expected


def test_in_sponsor_range_empty_ranges():
    assert _in_sponsor_range(100, []) is False


# -- Test 20: encode_image_base64 — roundtrip ---------------------------------

def test_encode_image_base64_roundtrip(tmp_path, tiny_jpeg_bytes):
    path = tmp_path / "test.jpg"
    path.write_bytes(tiny_jpeg_bytes)
    encoded = encode_image_base64(path)
    decoded = base64.standard_b64decode(encoded)
    assert decoded == tiny_jpeg_bytes


# -- Test 21: dedup_frames — identical collapse, different kept ---------------

def test_dedup_frames(tmp_path):
    # Create two identical red images and one different checkerboard image
    red_img = Image.new("RGB", (64, 64), color=(255, 0, 0))
    for name in ("frame_0001.jpg", "frame_0002.jpg"):
        red_img.save(tmp_path / name, format="JPEG")

    # Create a visually different image (blue with pattern)
    diff_img = Image.new("RGB", (64, 64), color=(0, 0, 255))
    for x in range(0, 64, 4):
        for y in range(0, 64, 4):
            diff_img.putpixel((x, y), (255, 255, 0))
    diff_img.save(tmp_path / "frame_0003.jpg", format="JPEG")

    frames = [tmp_path / f"frame_000{i}.jpg" for i in (1, 2, 3)]
    hashes = {f: imagehash.phash(Image.open(f)) for f in frames}

    # Mock laplacian_variance since it needs cv2.imread to work on real files
    # but we want to control which frame is "sharpest"
    def mock_laplacian(fp):
        # frame_0001 is "sharpest" in the red cluster
        return 100.0 if fp.name == "frame_0001.jpg" else 50.0

    with patch("video_to_essay.extract_frames.laplacian_variance", side_effect=mock_laplacian):
        result = dedup_frames(frames, hashes, max_hamming_distance=8)

    # Two identical reds should collapse to one; the blue should survive
    assert len(result) == 2
    result_names = {r.name for r in result}
    assert "frame_0001.jpg" in result_names  # sharpest red
    assert "frame_0003.jpg" in result_names  # different image
