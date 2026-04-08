"""Tests 22-28: place_images.py pure functions."""

import io
import json

from PIL import Image

from video_to_essay.place_images import (
    _number_figures,
    _resize_for_email,
    embed_images,
    format_frame_list,
    load_kept_frames,
)


# -- Test 22: format_frame_list — formats correctly ---------------------------

def test_format_frame_list():
    frames = [
        {"frame": "frame_0001.jpg", "timestamp": "00:00", "description": "A slide"},
        {"frame": "frame_0005.jpg", "timestamp": "00:20", "description": "A chart"},
    ]
    result = format_frame_list(frames)
    assert "- images/frame_0001.jpg [00:00] - A slide" in result
    assert "- images/frame_0005.jpg [00:20] - A chart" in result


def test_format_frame_list_custom_prefix():
    frames = [{"frame": "frame_0001.jpg", "timestamp": "00:00", "description": "Slide"}]
    result = format_frame_list(frames, image_prefix="pics/")
    assert result.startswith("- pics/frame_0001.jpg")


# -- Test 23: load_kept_frames — filters to present files --------------------

def test_load_kept_frames(tmp_path, tiny_jpeg_bytes):
    classifications = [
        {"frame": "frame_0001.jpg", "timestamp": "00:00", "description": "A"},
        {"frame": "frame_0002.jpg", "timestamp": "00:05", "description": "B"},
        {"frame": "frame_0003.jpg", "timestamp": "00:10", "description": "C"},
    ]
    cls_path = tmp_path / "classifications.json"
    cls_path.write_text(json.dumps(classifications))

    kept_dir = tmp_path / "kept"
    kept_dir.mkdir()
    (kept_dir / "frame_0001.jpg").write_bytes(tiny_jpeg_bytes)
    (kept_dir / "frame_0003.jpg").write_bytes(tiny_jpeg_bytes)

    result = load_kept_frames(cls_path, kept_dir)
    assert len(result) == 2
    assert result[0]["frame"] == "frame_0001.jpg"
    assert result[1]["frame"] == "frame_0003.jpg"


# -- Test 24: _number_figures — single image gets numbered --------------------

def test_number_figures_single():
    essay = "Some text\n\n![A chart](images/frame_0001.jpg)\n\nMore text"
    result, figures = _number_figures(essay)
    assert "*Figure 1: A chart*" in result
    assert figures == [(1, "A chart", "images/frame_0001.jpg")]


# -- Test 25: _number_figures — counter increments across multiple images -----

def test_number_figures_multiple():
    essay = (
        "Intro\n\n"
        "![First](images/frame_0001.jpg)\n\n"
        "Middle\n\n"
        "![Second](images/frame_0002.jpg)\n\n"
        "End\n\n"
        "![Third](images/frame_0003.jpg)"
    )
    result, figures = _number_figures(essay)
    assert len(figures) == 3
    assert figures[0][0] == 1
    assert figures[1][0] == 2
    assert figures[2][0] == 3
    assert "*Figure 1: First*" in result
    assert "*Figure 2: Second*" in result
    assert "*Figure 3: Third*" in result


# -- Test 26: _resize_for_email — output smaller, valid JPEG -----------------

def test_resize_for_email():
    # Create a large image
    large_img = Image.new("RGB", (1200, 800), color=(100, 150, 200))
    buf = io.BytesIO()
    large_img.save(buf, format="JPEG", quality=95)
    large_bytes = buf.getvalue()

    result = _resize_for_email(large_bytes, max_width=800, quality=70)
    assert len(result) < len(large_bytes)

    # Verify output is valid JPEG with correct dimensions
    out_img = Image.open(io.BytesIO(result))
    assert out_img.format == "JPEG"
    assert out_img.width <= 800


def test_resize_for_email_small_image_not_upscaled():
    small_img = Image.new("RGB", (400, 300), color=(100, 150, 200))
    buf = io.BytesIO()
    small_img.save(buf, format="JPEG", quality=95)
    small_bytes = buf.getvalue()

    result = _resize_for_email(small_bytes, max_width=800)
    out_img = Image.open(io.BytesIO(result))
    assert out_img.width == 400  # should not upscale


# -- Test 27: embed_images — replaces path with base64 -----------------------

def test_embed_images(tmp_frame_dir, tiny_jpeg_bytes):
    essay = "Text\n\n![A chart](images/frame_0001.jpg)\n\nMore"
    result = embed_images(essay, tmp_frame_dir, "images/")
    assert "data:image/jpeg;base64," in result
    assert "images/frame_0001.jpg" not in result


# -- Test 28: embed_images — missing frame leaves path unchanged --------------

def test_embed_images_missing_frame(tmp_path):
    essay = "![A chart](images/frame_9999.jpg)"
    result = embed_images(essay, tmp_path, "images/")
    assert result == "![A chart](images/frame_9999.jpg)"
