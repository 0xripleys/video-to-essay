"""Background worker that processes pipeline jobs from SQLite."""

import json
import threading
import time
import traceback
from pathlib import Path

from . import db
from .diarize import transcribe_with_deepgram
from .email_sender import send_essay
from .extract_frames import extract_and_classify, parse_transcript
from .filter_sponsors import filter_sponsors
from .place_images import (
    annotate_essay,
    embed_images,
    load_kept_frames,
    place_images_in_essay,
)
from .transcriber import (
    download_video,
    extract_video_id,
    fetch_video_metadata,
    transcript_to_essay,
)

RUNS_DIR = Path("runs")

STEP_DIRS: dict[str, str] = {
    "download": "00_download",
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


def _process_job(job: dict) -> None:
    """Run the full pipeline for a single job."""
    job_id = job["id"]
    url = job["youtube_url"]
    email = job["email"]

    video_id = extract_video_id(url)
    run_dir = RUNS_DIR / video_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Step 0: Download
    db.update_job(job_id, current_step="download")
    dl_dir = _step_dir(run_dir, "download")
    download_video(video_id, dl_dir)

    # Save metadata
    meta: dict = {"url": url, "video_id": video_id}
    try:
        yt_meta = fetch_video_metadata(video_id)
        meta.update(yt_meta)
    except Exception:
        pass
    meta_path = dl_dir / "metadata.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps(meta, indent=2))

    video_files = sorted(dl_dir.glob("video.*"))
    if not video_files:
        raise RuntimeError(f"No video file found in {dl_dir}")
    video_path = video_files[0]

    # Step 1: Transcript
    db.update_job(job_id, current_step="transcript")
    transcript_dir = _step_dir(run_dir, "transcript")
    transcribe_with_deepgram(video_path, transcript_dir, meta, force=False)

    # Step 2: Filter sponsors
    db.update_job(job_id, current_step="filter_sponsors")
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    transcript_text = (transcript_dir / "transcript.txt").read_text()
    cleaned, sponsor_ranges = filter_sponsors(transcript_text)
    (filter_dir / "transcript_clean.txt").write_text(cleaned)
    (filter_dir / "sponsor_segments.json").write_text(json.dumps(sponsor_ranges, indent=2))

    # Step 3: Essay
    db.update_job(job_id, current_step="essay")
    essay_dir = _step_dir(run_dir, "essay")
    essay_text = transcript_to_essay(cleaned)
    (essay_dir / "essay.md").write_text(essay_text)

    # Step 4: Extract frames
    db.update_job(job_id, current_step="frames")
    frames_dir = _step_dir(run_dir, "frames")
    transcript_entries = parse_transcript(transcript_text)
    extract_and_classify(
        video=video_path,
        output_dir=frames_dir,
        transcript_entries=transcript_entries,
        sponsor_ranges=sponsor_ranges,
    )

    # Step 5-6: Place images + annotate
    db.update_job(job_id, current_step="images")
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

    # Step 7: Send email
    db.update_job(job_id, current_step="email")
    video_title = meta.get("title", "Untitled Video")
    send_essay(email, video_title, final_essay)

    db.complete_job(job_id, video_title=video_title)
    print(f"Job {job_id} completed: {video_title}")


def _worker_loop(poll_interval: float = 5.0) -> None:
    """Poll for pending jobs and process them one at a time."""
    print(f"Worker started (polling every {poll_interval}s)")
    while True:
        try:
            job = db.claim_pending_job()
            if job:
                print(f"Processing job {job['id']}: {job['youtube_url']}")
                try:
                    _process_job(job)
                except Exception as e:
                    traceback.print_exc()
                    db.fail_job(job["id"], str(e))
                    print(f"Job {job['id']} failed: {e}")
            else:
                time.sleep(poll_interval)
        except Exception:
            traceback.print_exc()
            time.sleep(poll_interval)


def start_worker_thread(poll_interval: float = 5.0) -> threading.Thread:
    """Start the worker loop in a daemon thread."""
    t = threading.Thread(target=_worker_loop, args=(poll_interval,), daemon=True)
    t.start()
    return t
