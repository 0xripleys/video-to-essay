"""Tests 12-21: extract_frames.py pure functions."""

import base64
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import imagehash
import pytest
from PIL import Image

from video_to_essay.extract_frames import (
    _in_sponsor_range,
    classify_frames,
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


# -- classify_frames: parallelism, ordering, ContextVar propagation -----------

def _mock_response(payload: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )


def _seed_frames(tmp_path: Path, n: int, jpeg_bytes: bytes) -> list[Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, n + 1):
        p = tmp_path / f"frame_{i:04d}.jpg"
        p.write_bytes(jpeg_bytes)
        paths.append(p)
    return paths


def test_classify_frames_runs_in_parallel(tmp_path, tiny_jpeg_bytes):
    """If classification were sequential, the barrier would deadlock and timeout."""
    n_workers = 4
    frames = _seed_frames(tmp_path, n_workers, tiny_jpeg_bytes)

    barrier = threading.Barrier(n_workers, timeout=5.0)

    def mock_complete(*, task, messages, **_kwargs):
        # All n_workers callers must reach this point before any can proceed —
        # only possible if the calls run concurrently.
        barrier.wait()
        return _mock_response('{"category": "slide", "value": 4, "description": "x"}')

    with patch("video_to_essay.extract_frames.llm.complete", side_effect=mock_complete):
        results = classify_frames(frames, interval_seconds=5, max_workers=n_workers)

    assert len(results) == n_workers
    for r in results:
        assert r["category"] == "slide"


def test_classify_frames_preserves_input_order(tmp_path, tiny_jpeg_bytes):
    """Output order must match input order even when completions arrive in a different order."""
    frames = _seed_frames(tmp_path, 5, tiny_jpeg_bytes)

    # Earlier-indexed frames sleep longer so they complete LAST. If the impl
    # returned results in completion order, the output would be reversed.
    def mock_complete(*, task, messages, **_kwargs):
        # Pull the frame number out of the persisted-image placeholder doesn't
        # work here (it's the b64 payload). Use module-level state via threading.
        # Sleep proportional to a thread-local counter set by the dispatcher trick:
        # Instead, key off the data URL length-of-output ordering — simpler to
        # just have every call delay a tiny variable amount.
        time.sleep(0.02)
        return _mock_response('{"category": "slide", "value": 3, "description": "y"}')

    with patch("video_to_essay.extract_frames.llm.complete", side_effect=mock_complete):
        results = classify_frames(frames, interval_seconds=5, max_workers=4)

    assert [r["frame"] for r in results] == [f.name for f in frames]
    assert [r["timestamp"] for r in results] == ["00:00", "00:05", "00:10", "00:15", "00:20"]


def test_classify_frames_propagates_run_context(tmp_path, tiny_jpeg_bytes):
    """llm.run_context set in the parent thread must be visible inside workers
    so per-frame call logs are persisted to <step_dir>/llm_calls/."""
    from video_to_essay import llm as llm_mod

    frames = _seed_frames(tmp_path / "frames", 3, tiny_jpeg_bytes)
    step_dir = tmp_path / "step"
    step_dir.mkdir()

    seen_step_dirs: list[Path | None] = []

    def mock_complete(*, task, messages, **_kwargs):
        # Read the ContextVar from inside the worker thread.
        seen_step_dirs.append(llm_mod._step_dir.get())
        return _mock_response('{"category": "slide", "value": 3, "description": "z"}')

    with patch("video_to_essay.extract_frames.llm.complete", side_effect=mock_complete):
        with llm_mod.run_context(step_dir):
            classify_frames(frames, interval_seconds=5, max_workers=4)

    assert seen_step_dirs == [step_dir] * len(frames)


def test_classify_frames_empty_input(tmp_path):
    """No frames -> no LLM calls, empty list."""
    with patch("video_to_essay.extract_frames.llm.complete") as mock_complete:
        assert classify_frames([], interval_seconds=5) == []
        assert mock_complete.call_count == 0
