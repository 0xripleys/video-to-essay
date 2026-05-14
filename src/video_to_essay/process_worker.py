"""Process worker: runs the pipeline (transcript -> essay -> frames -> images) on downloaded videos."""

import json
import logging
import os
import re
import traceback
import time
from collections.abc import Iterator
from pathlib import Path

import httpx

import sentry_sdk

logger = logging.getLogger(__name__)

from . import db, llm
from .analytics import capture as track
from .diarize import transcribe_with_deepgram
from .extract_frames import extract_and_classify, parse_transcript
from .filter_sponsors import filter_sponsors
from .place_images import (
    annotate_essay,
    load_kept_frames,
    place_images_in_essay,
)
from .s3 import download_run, get_public_url, upload_run
from .summarize import summarize_essay
from .transcriber import transcript_to_essay

RUNS_DIR = Path("runs")
MAX_RETRIES = 3
TRANSIENT_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    ConnectionError,
    TimeoutError,
)
TRANSIENT_ERROR_MARKERS = (
    "ssl/tls alert bad record mac",
    "sslv3_alert_bad_record_mac",
    "bad record mac",
    "peer closed connection without sending complete message body",
    "incomplete chunked read",
    "remote protocol error",
    "connection reset",
    "connection aborted",
    "write operation timed out",
    "read operation timed out",
    "connect operation timed out",
    "overloaded_error",
    "anthropicerror - overloaded",
    "anthropicexception - overloaded",
)

STEP_DIRS: dict[str, str] = {
    "transcript": "01_transcript",
    "filter_sponsors": "02_filter_sponsors",
    "essay": "03_essay",
    "frames": "04_frames",
    "place_images": "05_place_images",
}


def _step_dir(run_dir: Path, step: str) -> Path:
    d = run_dir / STEP_DIRS[step]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_transient_error(exc: BaseException) -> bool:
    """Return True for transport/provider outages that are worth retrying.

    LiteLLM often wraps low-level httpx/OpenSSL failures in provider-specific
    API exceptions, so type checks alone miss the failures seen in production.
    """
    for chain_exc in _iter_exception_chain(exc):
        if isinstance(chain_exc, TRANSIENT_ERRORS):
            return True
        message = str(chain_exc).lower()
        if any(marker in message for marker in TRANSIENT_ERROR_MARKERS):
            return True
    return False


def _handle_transient_failure(video: dict, attempt: int) -> None:
    if attempt < MAX_RETRIES:
        wait = 2 ** attempt
        logger.warning(
            "Process: transient error on %s (attempt %d/%d), retrying in %ds",
            video["youtube_video_id"],
            attempt,
            MAX_RETRIES,
            wait,
        )
        logger.debug("Traceback:", exc_info=True)
        time.sleep(wait)
    else:
        sentry_sdk.capture_exception()
        logger.exception(
            "Process: failed %s after %d attempts",
            video["youtube_video_id"],
            MAX_RETRIES,
        )
        db.mark_video_failed(
            video["id"],
            f"Processing failed after {MAX_RETRIES} attempts: {traceback.format_exc()}",
        )


def _process_one(video: dict) -> None:
    """Run the full processing pipeline on a downloaded video."""
    youtube_video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / youtube_video_id
    dl_dir = run_dir / "00_download"

    download_run(youtube_video_id, step_dirs=["00_download"])

    # Find the video file, preferring clean names over yt-dlp intermediates (e.g. video.f396.mp4)
    all_video_files = sorted(dl_dir.glob("video.*"))
    if not all_video_files:
        raise RuntimeError(f"No video file found in {dl_dir}")
    video_files = [f for f in all_video_files if not re.search(r"\.f\d+\.", f.name)] or all_video_files
    video_path = video_files[0]

    # Load metadata
    meta_path = dl_dir / "metadata.json"
    meta: dict = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    # Step 1: Transcript (transcribe_with_deepgram has its own force=False skip)
    transcript_dir = _step_dir(run_dir, "transcript")
    transcribe_with_deepgram(video_path, transcript_dir, meta, force=False)
    transcript_text = (transcript_dir / "transcript.txt").read_text()

    # Step 2: Filter sponsors — skip LLM call if outputs already exist on disk.
    # Retries used to re-run the full pipeline; this keeps each completed step sticky.
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    clean_path = filter_dir / "transcript_clean.txt"
    sponsors_path = filter_dir / "sponsor_segments.json"
    if clean_path.exists() and sponsors_path.exists():
        logger.info("Process: %s filter_sponsors already done, skipping", youtube_video_id)
        cleaned = clean_path.read_text()
        sponsor_ranges = [tuple(r) for r in json.loads(sponsors_path.read_text())]
    else:
        with llm.run_context(filter_dir):
            cleaned, sponsor_ranges = filter_sponsors(transcript_text)
        clean_path.write_text(cleaned)
        sponsors_path.write_text(json.dumps(sponsor_ranges, indent=2))

    # Step 3: Essay — skip generation if essay.md already exists.
    # summarize_essay self-skips when "Key Takeaways" header is present, so always safe to call.
    essay_dir = _step_dir(run_dir, "essay")
    essay_path = essay_dir / "essay.md"
    if essay_path.exists():
        logger.info("Process: %s essay already generated, skipping", youtube_video_id)
    else:
        with llm.run_context(essay_dir):
            essay_text = transcript_to_essay(cleaned, video_id=youtube_video_id)
        essay_path.write_text(essay_text)
    summarize_essay(essay_path)
    essay_text = essay_path.read_text()

    # Step 4: Extract frames — skip if classifications.json already exists.
    frames_dir = _step_dir(run_dir, "frames")
    classifications_path = frames_dir / "classifications.json"
    if classifications_path.exists():
        logger.info("Process: %s frame classifications already exist, skipping", youtube_video_id)
    else:
        transcript_entries = parse_transcript(transcript_text)
        extract_and_classify(
            video=video_path,
            output_dir=frames_dir,
            transcript_entries=transcript_entries,
            sponsor_ranges=sponsor_ranges,
        )
    # Upload frame artifacts (classifications.json + per-frame llm_calls) before
    # the place-images branch. Run unconditionally — talking-head videos can yield
    # an empty kept set, but the classifications + call logs still need to land
    # on S3 for the runs viewer's audit trail.
    upload_run(youtube_video_id, step_dirs=["04_frames"])

    # Step 5-6: Place images + annotate — skip if final already exists.
    place_dir = _step_dir(run_dir, "place_images")
    final_path = place_dir / "essay_final.md"
    kept_dir = frames_dir / "kept"
    image_prefix = "../04_frames/kept/"

    if final_path.exists():
        logger.info("Process: %s place_images already done, skipping", youtube_video_id)
    else:
        kept = load_kept_frames(classifications_path, kept_dir)
        if kept:
            with llm.run_context(place_dir):
                with_images = place_images_in_essay(essay_text, kept, image_prefix)
                annotated = annotate_essay(with_images)
            # Rewrite relative image paths to public S3 URLs
            prefix_pattern = re.escape(image_prefix)
            def _to_s3_url(m: re.Match[str]) -> str:
                alt, filename = m.group(1), Path(m.group(2)).name
                url = get_public_url(f"runs/{youtube_video_id}/04_frames/kept/{filename}")
                return f"![{alt}]({url})"
            final_essay = re.sub(
                rf"!\[(.*?)\]\(({prefix_pattern}frame_\d+\.jpg)\)",
                _to_s3_url,
                annotated,
            )
        else:
            final_essay = essay_text
        final_path.write_text(final_essay)

    upload_run(youtube_video_id, step_dirs=[
        "01_transcript", "02_filter_sponsors", "03_essay", "05_place_images",
    ])

    db.mark_video_processed(video["id"])
    track("video_processed", {
        "youtube_video_id": youtube_video_id,
        "video_title": video.get("video_title", "untitled"),
    })
    logger.info("Process: completed %s (%s)", youtube_video_id, video.get("video_title", "untitled"))


def process_loop(poll_interval: float = 10.0) -> None:
    """Poll for videos pending processing and run the pipeline."""
    from .worker import init_logging, init_sentry
    init_sentry()
    init_logging()
    logger.info("Process worker started (polling every %ss)", poll_interval)
    for key in ("DATABASE_URL", "OPENROUTER_API_KEY", "DEEPGRAM_API_KEY", "S3_BUCKET_NAME"):
        val = os.environ.get(key)
        logger.info("  %s: %s", key, "set" if val else "NOT SET")
    while True:
        try:
            videos = db.get_videos_pending_processing()
            for video in videos:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        _process_one(video)
                        break
                    except Exception as exc:
                        if _is_transient_error(exc):
                            _handle_transient_failure(video, attempt)
                            continue
                        sentry_sdk.capture_exception()
                        logger.exception("Process: failed %s", video["youtube_video_id"])
                        db.mark_video_failed(video["id"], f"Processing failed: {traceback.format_exc()}")
                        break
        except Exception:
            sentry_sdk.capture_exception()
            logger.exception("Process worker: error in poll loop")
        time.sleep(poll_interval)
