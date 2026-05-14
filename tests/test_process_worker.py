"""Worker-level tests for src/video_to_essay/process_worker.py.

These tests exist to lock down behavior that's hard to spot from the CLI tests:
specifically that the worker uploads ALL step artifacts to S3 even when the
pipeline takes a degenerate branch (e.g. no kept frames).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest


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


@pytest.mark.parametrize(
    "exc",
    [
        httpx.WriteTimeout("The write operation timed out"),
        RuntimeError(
            "litellm.APIError: APIError: OpenrouterException - "
            "[SSL: SSLV3_ALERT_BAD_RECORD_MAC] ssl/tls alert bad record mac"
        ),
        RuntimeError(
            "litellm.APIConnectionError: AnthropicException - peer closed "
            "connection without sending complete message body "
            "(incomplete chunked read)"
        ),
        RuntimeError(
            "litellm.InternalServerError: AnthropicError - Overloaded"
        ),
    ],
)
def test_is_transient_error_recognizes_transport_failures(exc: Exception) -> None:
    from video_to_essay.process_worker import _is_transient_error

    assert _is_transient_error(exc)


def test_is_transient_error_walks_exception_chain() -> None:
    from video_to_essay.process_worker import _is_transient_error

    try:
        try:
            raise httpx.RemoteProtocolError("server disconnected")
        except httpx.RemoteProtocolError as inner:
            raise RuntimeError("wrapped by provider") from inner
    except RuntimeError as outer:
        assert _is_transient_error(outer)


def test_is_transient_error_rejects_content_errors() -> None:
    from video_to_essay.process_worker import _is_transient_error

    exc = TypeError("'NoneType' object is not subscriptable")

    assert not _is_transient_error(exc)


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


# -- Idempotency: each completed step is sticky across retries -----------------
#
# Before the per-step skip checks, a transient SSL error during frame
# classification would re-run essay generation (~17 min of DeepSeek) plus
# everything else on retry. These tests lock down that completed step outputs
# are detected and the corresponding LLM helper is NOT re-invoked.


def _seed_full_pipeline(run_dir: Path, *, with_classifications: bool = True,
                        with_final_essay: bool = False) -> None:
    """Seed every step's outputs so a re-run should be a complete no-op."""
    _seed_inputs(run_dir)
    (run_dir / "02_filter_sponsors").mkdir(parents=True)
    (run_dir / "02_filter_sponsors" / "transcript_clean.txt").write_text("[00:00] hi")
    (run_dir / "02_filter_sponsors" / "sponsor_segments.json").write_text("[]")
    (run_dir / "03_essay").mkdir(parents=True)
    (run_dir / "03_essay" / "essay.md").write_text(
        "# Essay\n\n## Key Takeaways\n\n- one\n\n---\n\n## Transcript\n\nbody"
    )
    if with_classifications:
        (run_dir / "04_frames" / "kept").mkdir(parents=True)
        (run_dir / "04_frames" / "classifications.json").write_text("[]")
    if with_final_essay:
        (run_dir / "05_place_images").mkdir(parents=True)
        (run_dir / "05_place_images" / "essay_final.md").write_text("# Essay")


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
def test_process_one_skips_filter_sponsors_when_outputs_exist(
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
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)
    video_id = "spVid"
    run_dir = tmp_path / video_id
    _seed_inputs(run_dir)
    # Pre-seed sponsor outputs only
    (run_dir / "02_filter_sponsors").mkdir(parents=True)
    (run_dir / "02_filter_sponsors" / "transcript_clean.txt").write_text("[00:00] cleaned text")
    (run_dir / "02_filter_sponsors" / "sponsor_segments.json").write_text("[[10, 20]]")

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_essay.return_value = "# Essay"
    mock_extract.side_effect = _frames_side_effect_no_kept().side_effect
    mock_load_kept.return_value = []
    mock_summarize.side_effect = lambda *a, **kw: None

    process_worker._process_one({
        "id": "row-sp", "youtube_video_id": video_id, "video_title": "t",
    })

    mock_filter.assert_not_called()
    # Sponsor ranges loaded from disk should be passed downstream as tuples
    extract_call = mock_extract.call_args
    assert extract_call.kwargs["sponsor_ranges"] == [(10, 20)]


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
def test_process_one_skips_essay_when_essay_md_exists(
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
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)
    video_id = "essVid"
    run_dir = tmp_path / video_id
    _seed_inputs(run_dir)
    (run_dir / "03_essay").mkdir(parents=True)
    pre_existing = "# Pre-existing essay\n\n## Key Takeaways\n\n- a\n\n---\n\n## Transcript\n\nx"
    (run_dir / "03_essay" / "essay.md").write_text(pre_existing)

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_filter.return_value = ("[00:00] hi", [])
    mock_extract.side_effect = _frames_side_effect_no_kept().side_effect
    mock_load_kept.return_value = []
    mock_summarize.side_effect = lambda *a, **kw: None

    process_worker._process_one({
        "id": "row-es", "youtube_video_id": video_id, "video_title": "t",
    })

    mock_essay.assert_not_called()
    # essay.md should be untouched
    assert (run_dir / "03_essay" / "essay.md").read_text() == pre_existing


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
def test_process_one_skips_extract_when_classifications_exist(
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
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)
    video_id = "frVid"
    run_dir = tmp_path / video_id
    _seed_inputs(run_dir)
    (run_dir / "04_frames" / "kept").mkdir(parents=True)
    (run_dir / "04_frames" / "classifications.json").write_text("[]")

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_filter.return_value = ("[00:00] hi", [])
    mock_essay.return_value = "# Essay"
    mock_load_kept.return_value = []
    mock_summarize.side_effect = lambda *a, **kw: None

    process_worker._process_one({
        "id": "row-fr", "youtube_video_id": video_id, "video_title": "t",
    })

    mock_extract.assert_not_called()


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
def test_process_one_fully_idempotent_when_all_outputs_exist(
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
    """The expensive case: a previous attempt completed all steps; this attempt
    must touch zero LLMs and just upload + mark processed."""
    from video_to_essay import process_worker

    monkeypatch.setattr(process_worker, "RUNS_DIR", tmp_path)
    video_id = "doneVid"
    run_dir = tmp_path / video_id
    _seed_full_pipeline(run_dir, with_classifications=True, with_final_essay=True)

    mock_transcribe.side_effect = lambda *a, **kw: None
    mock_summarize.side_effect = lambda *a, **kw: None

    process_worker._process_one({
        "id": "row-done", "youtube_video_id": video_id, "video_title": "t",
    })

    mock_filter.assert_not_called()
    mock_essay.assert_not_called()
    mock_extract.assert_not_called()
    mock_place.assert_not_called()
    mock_annotate.assert_not_called()
    mock_load_kept.assert_not_called()
    mock_db.mark_video_processed.assert_called_once_with("row-done")
