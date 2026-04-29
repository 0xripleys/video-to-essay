"""Integration test: full CLI pipeline chain (filter → essay → frames → place images).

Mocks all external API calls (Claude, ffmpeg) and tests that:
- Each step writes the expected output files
- Data flows correctly between steps (step N's output is step N+1's input)
- The final essay contains images and figure captions
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch



# ---------------------------------------------------------------------------
# Fixtures — realistic but minimal pipeline data
# ---------------------------------------------------------------------------

TRANSCRIPT = (
    "[00:00] Welcome to the show, today we're talking about Python.\n\n"
    "[01:00] Let's dive into type hints and why they matter for large codebases.\n\n"
    "[02:00] Before we continue, a word from our sponsor NordVPN. "
    "Use code PYTHON for 20 percent off.\n\n"
    "[03:00] Back to the topic. Type hints improve readability and catch bugs early.\n\n"
    "[04:00] In conclusion, use types everywhere in your Python code."
)

TRANSCRIPT_CLEAN = (
    "[00:00] Welcome to the show, today we're talking about Python.\n\n"
    "[01:00] Let's dive into type hints and why they matter for large codebases.\n\n"
    "[03:00] Back to the topic. Type hints improve readability and catch bugs early.\n\n"
    "[04:00] In conclusion, use types everywhere in your Python code."
)

SPONSOR_RANGES: list[tuple[int, int]] = [(120, 150)]

CANNED_ESSAY = (
    "# The Power of Python Type Hints\n\n"
    "Type hints have transformed how we write Python. "
    "They bring clarity to large codebases and catch bugs before runtime.\n\n"
    "## Why Type Hints Matter\n\n"
    "Large codebases benefit enormously from type annotations. "
    "They serve as living documentation that tools can verify.\n\n"
    "## Readability and Bug Prevention\n\n"
    "Type hints improve readability by making function signatures self-documenting. "
    "Static analyzers like mypy catch entire categories of bugs at development time "
    "rather than in production.\n\n"
    "## Conclusion\n\n"
    "Adopt type hints everywhere in your Python code. "
    "The upfront investment pays dividends in maintainability and correctness."
)

CLASSIFICATIONS = [
    {
        "frame": "frame_0002.jpg",
        "timestamp": "00:05",
        "category": "slide",
        "value": 4,
        "description": "Slide showing type hint syntax",
    },
    {
        "frame": "frame_0004.jpg",
        "timestamp": "00:15",
        "category": "code",
        "value": 5,
        "description": "Code example with type annotations",
    },
    {
        "frame": "frame_0003.jpg",
        "timestamp": "00:10",
        "category": "talking_head",
        "value": 2,
        "description": "Speaker talking to camera",
    },
]

IMAGE_PREFIX = "../04_frames/kept/"

ESSAY_WITH_IMAGES = (
    "# The Power of Python Type Hints\n\n"
    "Type hints have transformed how we write Python. "
    "They bring clarity to large codebases and catch bugs before runtime.\n\n"
    f"![Slide showing type hint syntax]({IMAGE_PREFIX}frame_0002.jpg)\n\n"
    "## Why Type Hints Matter\n\n"
    "Large codebases benefit enormously from type annotations. "
    "They serve as living documentation that tools can verify.\n\n"
    "## Readability and Bug Prevention\n\n"
    "Type hints improve readability by making function signatures self-documenting. "
    "Static analyzers like mypy catch entire categories of bugs at development time "
    "rather than in production.\n\n"
    f"![Code example with type annotations]({IMAGE_PREFIX}frame_0004.jpg)\n\n"
    "## Conclusion\n\n"
    "Adopt type hints everywhere in your Python code. "
    "The upfront investment pays dividends in maintainability and correctness."
)

ANNOTATED_ESSAY = ESSAY_WITH_IMAGES.replace(
    f"![Slide showing type hint syntax]({IMAGE_PREFIX}frame_0002.jpg)",
    f"![Slide showing type hint syntax]({IMAGE_PREFIX}frame_0002.jpg)\n"
    "*Figure 1: Slide showing type hint syntax*",
).replace(
    f"![Code example with type annotations]({IMAGE_PREFIX}frame_0004.jpg)",
    f"![Code example with type annotations]({IMAGE_PREFIX}frame_0004.jpg)\n"
    "*Figure 2: Code example with type annotations*",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_filesystem(run_dir: Path, tiny_jpeg_bytes: bytes) -> None:
    """Create the prerequisite files that steps 0-1 would have produced."""
    # Step 0: download
    dl_dir = run_dir / "00_download"
    dl_dir.mkdir(parents=True)
    (dl_dir / "video.mp4").write_bytes(b"\x00" * 16)
    (dl_dir / "metadata.json").write_text(json.dumps({
        "video_id": "test12345ab",
        "url": "https://www.youtube.com/watch?v=test12345ab",
    }))

    # Step 1: transcript
    transcript_dir = run_dir / "01_transcript"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "transcript.txt").write_text(TRANSCRIPT)


def _mock_extract_and_classify(
    tiny_jpeg_bytes: bytes,
) -> MagicMock:
    """Return a mock for extract_and_classify that writes frames + classifications."""

    def side_effect(
        video: Path,
        output_dir: Path,
        **kwargs: object,
    ) -> list[dict]:
        # Write kept frames
        kept_dir = output_dir / "kept"
        kept_dir.mkdir(parents=True, exist_ok=True)
        for c in CLASSIFICATIONS:
            if c["category"] != "talking_head" and c["value"] >= 3:
                (kept_dir / c["frame"]).write_bytes(tiny_jpeg_bytes)

        # Write full classifications (including filtered-out ones)
        (output_dir / "classifications.json").write_text(
            json.dumps(CLASSIFICATIONS, indent=2)
        )

        return [c for c in CLASSIFICATIONS if c["category"] != "talking_head" and c["value"] >= 3]

    mock = MagicMock(side_effect=side_effect)
    return mock


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@patch("video_to_essay.main.annotate_essay")
@patch("video_to_essay.main.place_images_in_essay")
@patch("video_to_essay.main.extract_and_classify")
@patch("video_to_essay.main.summarize_essay")
@patch("video_to_essay.main.transcript_to_essay")
@patch("video_to_essay.main.filter_sponsors")
def test_pipeline_happy_path(
    mock_filter: MagicMock,
    mock_essay: MagicMock,
    mock_summarize: MagicMock,
    mock_frames: MagicMock,
    mock_place: MagicMock,
    mock_annotate: MagicMock,
    tmp_path: Path,
    tiny_jpeg_bytes: bytes,
) -> None:
    from video_to_essay.main import (
        _step_essay,
        _step_extract_frames,
        _step_filter_sponsors,
        _step_place_images,
    )

    video_id = "test12345ab"
    run_dir = tmp_path / video_id
    _seed_filesystem(run_dir, tiny_jpeg_bytes)

    # Configure mocks
    mock_filter.return_value = (TRANSCRIPT_CLEAN, SPONSOR_RANGES)
    mock_essay.return_value = CANNED_ESSAY
    mock_summarize.return_value = None
    mock_frames.side_effect = _mock_extract_and_classify(tiny_jpeg_bytes).side_effect
    mock_place.return_value = ESSAY_WITH_IMAGES
    mock_annotate.return_value = ANNOTATED_ESSAY

    # -----------------------------------------------------------------------
    # Step 2: Filter sponsors
    # -----------------------------------------------------------------------
    assert _step_filter_sponsors(video_id, run_dir, force=False) is True

    filter_dir = run_dir / "02_filter_sponsors"
    clean_text = (filter_dir / "transcript_clean.txt").read_text()
    assert "NordVPN" not in clean_text
    assert "type hints" in clean_text.lower()

    segments = json.loads((filter_dir / "sponsor_segments.json").read_text())
    assert segments == [[120, 150]]

    # filter_sponsors was called with the original transcript
    mock_filter.assert_called_once_with(TRANSCRIPT, model=None)

    # -----------------------------------------------------------------------
    # Step 3: Essay
    # -----------------------------------------------------------------------
    assert _step_essay(video_id, run_dir, force=False) is True

    essay_path = run_dir / "03_essay" / "essay.md"
    assert essay_path.read_text() == CANNED_ESSAY

    # transcript_to_essay received the *cleaned* transcript, not the original
    mock_essay.assert_called_once()
    call_args = mock_essay.call_args
    assert call_args.args[0] == TRANSCRIPT_CLEAN or call_args.kwargs.get("transcript") == TRANSCRIPT_CLEAN
    # Also check video_id was passed
    assert call_args.kwargs.get("video_id") == video_id or (
        len(call_args.args) > 1 and call_args.args[1] == video_id
    )

    # -----------------------------------------------------------------------
    # Step 4: Extract frames
    # -----------------------------------------------------------------------
    assert _step_extract_frames(video_id, run_dir, force=False) is True

    frames_dir = run_dir / "04_frames"
    assert (frames_dir / "classifications.json").exists()

    kept_dir = frames_dir / "kept"
    kept_files = sorted(p.name for p in kept_dir.glob("frame_*.jpg"))
    assert kept_files == ["frame_0002.jpg", "frame_0004.jpg"]

    # extract_and_classify got the sponsor ranges
    mock_frames.assert_called_once()
    frame_kwargs = mock_frames.call_args.kwargs
    assert frame_kwargs.get("sponsor_ranges") == SPONSOR_RANGES

    # -----------------------------------------------------------------------
    # Step 5-6: Place images + annotate
    # -----------------------------------------------------------------------
    assert _step_place_images(video_id, run_dir, embed=False, force=False) is True

    place_dir = run_dir / "05_place_images"

    essay_with_images = (place_dir / "essay_with_images.md").read_text()
    assert "![" in essay_with_images
    assert IMAGE_PREFIX in essay_with_images

    essay_final = (place_dir / "essay_final.md").read_text()
    assert "*Figure 1:" in essay_final
    assert "*Figure 2:" in essay_final

    # place_images_in_essay received the canned essay and the 2 kept frames
    mock_place.assert_called_once()
    place_args = mock_place.call_args
    assert place_args.args[0] == CANNED_ESSAY
    placed_frames = place_args.args[1]
    assert len(placed_frames) == 2
    assert placed_frames[0]["frame"] == "frame_0002.jpg"
    assert placed_frames[1]["frame"] == "frame_0004.jpg"

    # annotate_essay received the essay with images placed
    mock_annotate.assert_called_once_with(ESSAY_WITH_IMAGES)

    # -----------------------------------------------------------------------
    # Every mock called exactly once
    # (summarize_essay is called from the `run` CLI command, not _step_essay)
    # -----------------------------------------------------------------------
    assert mock_filter.call_count == 1
    assert mock_essay.call_count == 1
    assert mock_frames.call_count == 1
    assert mock_place.call_count == 1
    assert mock_annotate.call_count == 1
