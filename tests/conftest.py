"""Shared fixtures for pure (no-infrastructure) tests."""

import io

import pytest
from PIL import Image


@pytest.fixture(scope="session")
def tiny_jpeg_bytes() -> bytes:
    """A minimal valid 4x4 red JPEG image."""
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def tmp_frame_dir(tmp_path, tiny_jpeg_bytes):
    """Temp directory populated with frame_0001.jpg and frame_0002.jpg."""
    for name in ("frame_0001.jpg", "frame_0002.jpg"):
        (tmp_path / name).write_bytes(tiny_jpeg_bytes)
    return tmp_path


@pytest.fixture()
def sample_single_speaker_transcript() -> str:
    return (
        "[00:00] Welcome to the show everyone.\n\n"
        "[02:00] Today we're talking about investing.\n\n"
        "[04:00] Let's dive into portfolio construction.\n\n"
        "[06:00] Thanks for watching, see you next time."
    )


@pytest.fixture()
def sample_multi_speaker_transcript() -> str:
    return (
        "**Alice** [00:00]\nWelcome to the show everyone.\n\n"
        "**Bob** [02:00]\nThanks for having me Alice.\n\n"
        "**Alice** [04:00]\nLet's talk about investing.\n\n"
        "**Bob** [06:00]\nGreat topic, I love portfolio construction."
    )


@pytest.fixture()
def sample_essay_md() -> str:
    return (
        "# My Great Video Essay\n\n"
        "## Key Takeaways\n\n"
        "- Point one about investing\n\n"
        "- Point two about portfolios\n\n"
        "---\n\n"
        "## Introduction\n\n"
        "This is the introduction paragraph.\n\n"
        "![A chart](images/frame_0001.jpg)\n\n"
        "## Main Section\n\n"
        "This is the main content of the essay with more details.\n\n"
        "![A slide](images/frame_0002.jpg)\n\n"
        "## Conclusion\n\n"
        "This is the conclusion."
    )
