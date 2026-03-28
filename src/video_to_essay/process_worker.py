"""Process worker: runs the pipeline (transcript -> essay -> frames -> images) on downloaded videos."""

import json
import os
import traceback
import time
from pathlib import Path

from . import db
from .diarize import transcribe_with_deepgram
from .extract_frames import extract_and_classify, parse_transcript
from .filter_sponsors import filter_sponsors
from .place_images import (
    annotate_essay,
    embed_images,
    load_kept_frames,
    place_images_in_essay,
)
from .transcriber import transcript_to_essay

RUNS_DIR = Path("runs")

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


def _process_one(video: dict) -> None:
    """Run the full processing pipeline on a downloaded video."""
    youtube_video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / youtube_video_id
    dl_dir = run_dir / "00_download"

    # Find the video file
    video_files = sorted(dl_dir.glob("video.*"))
    if not video_files:
        raise RuntimeError(f"No video file found in {dl_dir}")
    video_path = video_files[0]

    # Load metadata
    meta_path = dl_dir / "metadata.json"
    meta: dict = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    # Step 1: Transcript
    transcript_dir = _step_dir(run_dir, "transcript")
    transcribe_with_deepgram(video_path, transcript_dir, meta, force=False)

    # Step 2: Filter sponsors
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    transcript_text = (transcript_dir / "transcript.txt").read_text()
    cleaned, sponsor_ranges = filter_sponsors(transcript_text)
    (filter_dir / "transcript_clean.txt").write_text(cleaned)
    (filter_dir / "sponsor_segments.json").write_text(json.dumps(sponsor_ranges, indent=2))

    # Step 3: Essay
    essay_dir = _step_dir(run_dir, "essay")
    essay_text = transcript_to_essay(cleaned)
    (essay_dir / "essay.md").write_text(essay_text)

    # Step 4: Extract frames
    frames_dir = _step_dir(run_dir, "frames")
    transcript_entries = parse_transcript(transcript_text)
    extract_and_classify(
        video=video_path,
        output_dir=frames_dir,
        transcript_entries=transcript_entries,
        sponsor_ranges=sponsor_ranges,
    )

    # Step 5-6: Place images + annotate
    place_dir = _step_dir(run_dir, "place_images")
    kept_dir = frames_dir / "kept"
    classifications_path = frames_dir / "classifications.json"
    image_prefix = "../04_frames/kept/"

    kept = load_kept_frames(classifications_path, kept_dir)
    if kept:
        with_images = place_images_in_essay(essay_text, kept, image_prefix)
        annotated = annotate_essay(with_images)
        final_essay = embed_images(annotated, kept_dir, image_prefix)
    else:
        final_essay = essay_text

    (place_dir / "essay_final.md").write_text(final_essay)

    db.mark_video_processed(video["id"])
    print(f"Process: completed {youtube_video_id} ({video.get('video_title', 'untitled')})")


def process_loop(poll_interval: float = 10.0) -> None:
    """Poll for videos pending processing and run the pipeline."""
    print(f"Process worker started (polling every {poll_interval}s)")
    for key in ("DATABASE_URL", "ANTHROPIC_API_KEY", "DEEPGRAM_API_KEY"):
        val = os.environ.get(key)
        print(f"  {key}: {'set' if val else 'NOT SET'}")
    while True:
        try:
            videos = db.get_videos_pending_processing()
            for video in videos:
                try:
                    _process_one(video)
                except Exception:
                    traceback.print_exc()
                    db.mark_video_failed(video["id"], f"Processing failed: {traceback.format_exc()}")
                    print(f"Process: failed {video['youtube_video_id']}")
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
