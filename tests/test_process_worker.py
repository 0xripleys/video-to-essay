"""Worker-level tests for src/video_to_essay/process_worker.py.

These tests exist to lock down behavior that's hard to spot from the CLI tests:
specifically that the worker uploads ALL step artifacts to S3 even when the
pipeline takes a degenerate branch (e.g. no kept frames).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _seed_inputs(run_dir: Path) -> None:
    """Mimic what download_run + transcribe_with_deepgram would have produced."""
    (run_dir / "00_download").mkdir(parents=True)
    (run_dir / "00_download" / "video.mp4").write_bytes(b"\x00" * 16)
    (run_dir / "00_download" / "metadata.json").write_text(
        json.dumps({"title": "test", "channel": "test"})
    )
    (run_dir / "01_transcript").mkdir(parents=True)
    (run_dir / "01_transcript" / "transcript.txt").write_text("[00:00] hi")


def _frames_side_effect_no_kept() -> MagicMock:
    """extract_and_classify writes classifications.json but kept/ is empty."""
    def side_effect(*, video, output_dir, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "kept").mkdir(parents=True, exist_ok=True)
        (output_dir / "classifications.json").write_text(json.dumps([
            {
                "frame": "frame_0001.jpg",
                "timestamp": "00:00",
                "category": "talking_head",
                "value": 1,
                "description": "speaker only",
            },
        ]))
        return []
    return MagicMock(side_effect=side_effect)


@patch("video_to_essay.process_worker.track")
@patch("video_to_essay.process_worker.db")
@patch("video_to_essay.process_worker.upload_run")
@patch("video_to_essay.process_worker.download_run")
@patch("video_to_essay.process_worker.summarize_essay")
@patch("video_to_essay.process_worker.annotate_essay")
@patch("video_to_essay.process_worker.place_images_in_essay")
@patch("video_to_essay.process_worker.load_kept_frames")
@patch("video_to_essay.process_worker.extract_and_classify")
@patch("video_to_essay.process_worker.transcript_to_essay")
@patch("video_to_essay.process_worker.filter_sponsors")
@patch("video_to_essay.process_worker.transcribe_with_deepgram")
def test_process_one_uploads_04_frames_even_when_no_kept(
    mock_transcribe: MagicMock,
    mock_filter: MagicMock,
    mock_essay: MagicMock,
    mock_extract: MagicMock,
    mock_load_kept: MagicMock,
    mock_place: MagicMock,
    mock_annotate: MagicMock,
    mock_summarize: MagicMock,
    mock_download: MagicMock,
    mock_upload: MagicMock,
    mock_db: MagicMock,
    mock_track: MagicMock,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Regression test for the bug where 04_frames was never uploaded if every
    sampled frame was filtered out (talking-head videos)."""
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)

    video_id = "noFramesVid"
    run_dir = tmp_path / video_id
    _seed_inputs(run_dir)

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_filter.return_value = ("[00:00] hi", [])
    mock_essay.return_value = "# Essay"
    mock_extract.side_effect = _frames_side_effect_no_kept().side_effect
    mock_load_kept.return_value = []  # no useful frames
    mock_summarize.side_effect = lambda *a, **kw: None

    process_worker._process_one({
        "id": "row-1",
        "youtube_video_id": video_id,
        "video_title": "Talking head",
    })

    # The bug: upload_run was only called with 04_frames inside the `if kept:`
    # branch, so when kept was empty (talking-head video) the classifications +
    # llm_calls never landed on S3.
    upload_calls = [c for c in mock_upload.call_args_list]
    step_dirs_uploaded = [
        c.kwargs.get("step_dirs") or (c.args[1] if len(c.args) > 1 else None)
        for c in upload_calls
    ]
    flat = [s for sublist in step_dirs_uploaded if sublist for s in sublist]
    assert "04_frames" in flat, (
        f"Expected upload_run to include '04_frames'; got step_dirs={step_dirs_uploaded}"
    )

    # place_images should NOT have run (no kept frames)
    assert mock_place.call_count == 0
    assert mock_annotate.call_count == 0

    # Final essay equals the original (no images placed)
    final = (run_dir / "05_place_images" / "essay_final.md").read_text()
    assert final == "# Essay"


@patch("video_to_essay.process_worker.track")
@patch("video_to_essay.process_worker.db")
@patch("video_to_essay.process_worker.upload_run")
@patch("video_to_essay.process_worker.download_run")
@patch("video_to_essay.process_worker.summarize_essay")
@patch("video_to_essay.process_worker.annotate_essay")
@patch("video_to_essay.process_worker.place_images_in_essay")
@patch("video_to_essay.process_worker.load_kept_frames")
@patch("video_to_essay.process_worker.extract_and_classify")
@patch("video_to_essay.process_worker.transcript_to_essay")
@patch("video_to_essay.process_worker.filter_sponsors")
@patch("video_to_essay.process_worker.transcribe_with_deepgram")
@patch("video_to_essay.process_worker.get_public_url")
def test_process_one_uploads_04_frames_when_frames_kept(
    mock_get_url: MagicMock,
    mock_transcribe: MagicMock,
    mock_filter: MagicMock,
    mock_essay: MagicMock,
    mock_extract: MagicMock,
    mock_load_kept: MagicMock,
    mock_place: MagicMock,
    mock_annotate: MagicMock,
    mock_summarize: MagicMock,
    mock_download: MagicMock,
    mock_upload: MagicMock,
    mock_db: MagicMock,
    mock_track: MagicMock,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Sanity check the happy path still uploads 04_frames exactly once."""
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)

    video_id = "happyVid"
    run_dir = tmp_path / video_id
    _seed_inputs(run_dir)

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_filter.return_value = ("[00:00] hi", [])
    mock_essay.return_value = "# Essay\n\n![x](../04_frames/kept/frame_0001.jpg)"
    mock_extract.side_effect = _frames_side_effect_no_kept().side_effect
    mock_load_kept.return_value = [{"frame": "frame_0001.jpg", "timestamp": "00:01"}]
    mock_place.return_value = "# Essay\n\n![x](../04_frames/kept/frame_0001.jpg)"
    mock_annotate.return_value = "# Essay annotated"
    mock_summarize.side_effect = lambda *a, **kw: None
    mock_get_url.return_value = "https://example.com/frame.jpg"

    process_worker._process_one({
        "id": "row-2",
        "youtube_video_id": video_id,
        "video_title": "Has frames",
    })

    step_dirs_uploaded = [
        c.kwargs.get("step_dirs") or (c.args[1] if len(c.args) > 1 else None)
        for c in mock_upload.call_args_list
    ]
    flat = [s for sublist in step_dirs_uploaded if sublist for s in sublist]
    assert flat.count("04_frames") == 1, (
        f"Expected exactly one upload of 04_frames; got step_dirs={step_dirs_uploaded}"
    )
