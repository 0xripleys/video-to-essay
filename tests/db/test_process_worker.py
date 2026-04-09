"""Process worker integration test: real Postgres + mocked external services.

Tests _process_one with all external calls mocked (S3, Claude, Deepgram, ffmpeg)
to verify the glue logic: data flows between steps, S3 URLs replace relative paths,
uploads happen in the right order, and DB state transitions correctly.
"""

import io
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from PIL import Image

from video_to_essay import db

# ---------------------------------------------------------------------------
# Fixtures
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
    "Type hints have transformed how we write Python.\n\n"
    "## Why Type Hints Matter\n\n"
    "Large codebases benefit from type annotations.\n\n"
    "## Conclusion\n\n"
    "Adopt type hints everywhere."
)

# summarize_essay prepends Key Takeaways to the essay in-place
ESSAY_AFTER_SUMMARY = (
    "# The Power of Python Type Hints\n\n"
    "## Key Takeaways\n\n"
    "- Type hints catch bugs early\n\n"
    "---\n\n"
    "## Transcript\n\n"
    "Type hints have transformed how we write Python.\n\n"
    "## Why Type Hints Matter\n\n"
    "Large codebases benefit from type annotations.\n\n"
    "## Conclusion\n\n"
    "Adopt type hints everywhere."
)

IMAGE_PREFIX = "../04_frames/kept/"

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
]

ESSAY_WITH_IMAGES = (
    "# The Power of Python Type Hints\n\n"
    "## Key Takeaways\n\n"
    "- Type hints catch bugs early\n\n"
    "---\n\n"
    "## Transcript\n\n"
    "Type hints have transformed how we write Python.\n\n"
    f"![Slide showing type hint syntax]({IMAGE_PREFIX}frame_0002.jpg)\n\n"
    "## Why Type Hints Matter\n\n"
    "Large codebases benefit from type annotations.\n\n"
    f"![Code example with type annotations]({IMAGE_PREFIX}frame_0004.jpg)\n\n"
    "## Conclusion\n\n"
    "Adopt type hints everywhere."
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


def _tiny_jpeg() -> bytes:
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def _make_video_row() -> dict:
    """Insert prerequisite DB rows and return the video dict."""
    db.create_user(f"u{_uniq()}@test.com", f"wos_{_uniq()}")
    yt_channel_id = f"UC{_uniq()}"
    db.create_channel(yt_channel_id, "Test Channel")
    channel = db.get_channel_by_youtube_id(yt_channel_id)

    yt_video_id = f"v{_uniq()}"
    db.create_video(
        youtube_video_id=yt_video_id,
        youtube_url=f"https://www.youtube.com/watch?v={yt_video_id}",
        channel_id=channel["id"],
        video_title="Test Video about Python",
    )
    db.mark_video_downloaded(db.get_video_by_youtube_id(yt_video_id)["id"], "Test Video about Python")
    return db.get_video_by_youtube_id(yt_video_id)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@patch("video_to_essay.process_worker.track")
@patch("video_to_essay.process_worker.get_public_url")
@patch("video_to_essay.process_worker.upload_run")
@patch("video_to_essay.process_worker.download_run")
@patch("video_to_essay.process_worker.annotate_essay")
@patch("video_to_essay.process_worker.place_images_in_essay")
@patch("video_to_essay.process_worker.extract_and_classify")
@patch("video_to_essay.process_worker.summarize_essay")
@patch("video_to_essay.process_worker.transcript_to_essay")
@patch("video_to_essay.process_worker.filter_sponsors")
@patch("video_to_essay.process_worker.transcribe_with_deepgram")
def test_process_one_happy_path(
    mock_transcribe: MagicMock,
    mock_filter: MagicMock,
    mock_essay: MagicMock,
    mock_summarize: MagicMock,
    mock_frames: MagicMock,
    mock_place: MagicMock,
    mock_annotate: MagicMock,
    mock_download_run: MagicMock,
    mock_upload_run: MagicMock,
    mock_get_public_url: MagicMock,
    mock_track: MagicMock,
    tmp_path: Path,
    pg_container,
) -> None:
    from video_to_essay.process_worker import _process_one

    video = _make_video_row()
    yt_id = video["youtube_video_id"]
    tiny = _tiny_jpeg()

    # Point RUNS_DIR to tmp so we don't litter the real filesystem
    with patch("video_to_essay.process_worker.RUNS_DIR", tmp_path):
        run_dir = tmp_path / yt_id

        # -- Mock: download_run seeds the filesystem (simulates S3 download) --
        def fake_download_run(vid, step_dirs=None):
            dl_dir = tmp_path / vid / "00_download"
            dl_dir.mkdir(parents=True, exist_ok=True)
            (dl_dir / "video.mp4").write_bytes(b"\x00" * 16)
            (dl_dir / "metadata.json").write_text(json.dumps({
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
            }))

        mock_download_run.side_effect = fake_download_run

        # -- Mock: transcribe_with_deepgram writes transcript.txt --
        def fake_transcribe(video_path, output_dir, meta, force=False):
            (output_dir / "transcript.txt").write_text(TRANSCRIPT)

        mock_transcribe.side_effect = fake_transcribe

        # -- Mock: filter_sponsors --
        mock_filter.return_value = (TRANSCRIPT_CLEAN, SPONSOR_RANGES)

        # -- Mock: transcript_to_essay --
        mock_essay.return_value = CANNED_ESSAY

        # -- Mock: summarize_essay writes in-place --
        def fake_summarize(essay_path, force=False):
            essay_path.write_text(ESSAY_AFTER_SUMMARY)

        mock_summarize.side_effect = fake_summarize

        # -- Mock: extract_and_classify writes frames + classifications --
        def fake_extract(video, output_dir, **kwargs):
            kept_dir = output_dir / "kept"
            kept_dir.mkdir(parents=True, exist_ok=True)
            for c in CLASSIFICATIONS:
                (kept_dir / c["frame"]).write_bytes(tiny)
            (output_dir / "classifications.json").write_text(
                json.dumps(CLASSIFICATIONS, indent=2)
            )
            return CLASSIFICATIONS

        mock_frames.side_effect = fake_extract

        # -- Mock: place_images_in_essay --
        mock_place.return_value = ESSAY_WITH_IMAGES

        # -- Mock: annotate_essay --
        mock_annotate.return_value = ANNOTATED_ESSAY

        # -- Mock: get_public_url returns predictable S3 URLs --
        def fake_public_url(key):
            return f"https://test-bucket.s3.us-east-1.amazonaws.com/{key}"

        mock_get_public_url.side_effect = fake_public_url

        # -- Mock: upload_run is a no-op --
        mock_upload_run.return_value = None

        # ===================================================================
        # Run the worker
        # ===================================================================
        _process_one(video)

        # ===================================================================
        # Assertions
        # ===================================================================

        # -- 1. S3 download happened for 00_download --
        mock_download_run.assert_called_once_with(yt_id, step_dirs=["00_download"])

        # -- 2. transcript_to_essay got the CLEANED transcript --
        mock_essay.assert_called_once()
        assert mock_essay.call_args.args[0] == TRANSCRIPT_CLEAN

        # -- 3. place_images_in_essay got the essay AFTER summarization --
        mock_place.assert_called_once()
        assert mock_place.call_args.args[0] == ESSAY_AFTER_SUMMARY

        # -- 4. Frames uploaded BEFORE other steps --
        upload_calls = mock_upload_run.call_args_list
        assert len(upload_calls) == 2
        # First upload: frames
        assert upload_calls[0] == call(yt_id, step_dirs=["04_frames"])
        # Second upload: everything else
        assert upload_calls[1] == call(
            yt_id,
            step_dirs=["01_transcript", "02_filter_sponsors", "03_essay", "05_place_images"],
        )

        # -- 5. Final essay has S3 URLs, not relative paths --
        final_essay = (run_dir / "05_place_images" / "essay_final.md").read_text()
        assert IMAGE_PREFIX not in final_essay
        assert "https://test-bucket.s3.us-east-1.amazonaws.com/" in final_essay
        assert f"runs/{yt_id}/04_frames/kept/frame_0002.jpg" in final_essay
        assert f"runs/{yt_id}/04_frames/kept/frame_0004.jpg" in final_essay

        # -- 6. DB row is marked processed --
        updated = db.get_video_by_youtube_id(yt_id)
        assert updated["processed_at"] is not None
        assert updated["error"] is None

        # -- 7. Analytics event fired --
        mock_track.assert_called_once()
        assert mock_track.call_args.args[0] == "video_processed"
