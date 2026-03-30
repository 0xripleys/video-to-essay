"""Download worker: downloads videos via yt-dlp, uploads to S3, marks as downloaded."""

import json
import os
import traceback
import time
from pathlib import Path

from . import db
from .s3 import upload_run
from .transcriber import download_video, fetch_video_metadata

RUNS_DIR = Path("runs")


def _download_one(video: dict) -> None:
    """Download a single video locally."""
    video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / video_id / "00_download"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Skip if already downloaded locally
    existing = sorted(run_dir.glob("video.*"))
    if existing:
        print(f"  [{video_id}] Video already exists locally, skipping download")
    else:
        print(f"  [{video_id}] Downloading video...")
        download_video(video_id, run_dir)
        print(f"  [{video_id}] Download complete")

    # Save metadata
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        print(f"  [{video_id}] Fetching metadata...")
        meta: dict = {"url": video["youtube_url"], "video_id": video_id}
        try:
            yt_meta = fetch_video_metadata(video_id)
            meta.update(yt_meta)
        except Exception as e:
            print(f"  [{video_id}] Metadata fetch failed: {e}")
        meta_path.write_text(json.dumps(meta, indent=2))

    # Get title from metadata
    title = video.get("video_title")
    if not title and meta_path.exists():
        meta_data = json.loads(meta_path.read_text())
        title = meta_data.get("title")

    print(f"  [{video_id}] Uploading to S3...")
    upload_run(video_id, step_dirs=["00_download"])
    db.mark_video_downloaded(video["id"], video_title=title)
    print(f"  [{video_id}] Done ({title or 'untitled'})")


def download_loop(poll_interval: float = 10.0) -> None:
    """Poll for videos pending download and process them."""
    print(f"Download worker started (polling every {poll_interval}s)")
    for key in ("DATABASE_URL", "S3_BUCKET_NAME", "PROXY_URL"):
        val = os.environ.get(key)
        print(f"  {key}: {'set' if val else 'NOT SET'}")
    while True:
        try:
            print("Polling...")
            videos = db.get_videos_pending_download()
            if videos:
                print(f"Found {len(videos)} video(s) pending download")
            for video in videos:
                vid = video["youtube_video_id"]
                print(f"  [{vid}] Starting download for {video.get('youtube_url', vid)}")
                try:
                    _download_one(video)
                except Exception:
                    traceback.print_exc()
                    db.mark_video_failed(video["id"], f"Download failed: {traceback.format_exc()}")
                    print(f"  [{vid}] FAILED")
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
