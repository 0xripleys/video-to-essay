"""Download worker: downloads videos via yt-dlp, uploads to S3, marks as downloaded."""

import json
import os
import subprocess
import traceback
import time
from pathlib import Path

import sentry_sdk

from . import db
from .s3 import upload_run
from .transcriber import download_video, fetch_video_metadata

RUNS_DIR = Path("runs")


def _download_one(video: dict) -> None:
    """Download a single video locally."""
    video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / video_id / "00_download"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Clean up partial downloads
    for part_file in run_dir.glob("video.*.part"):
        print(f"  [{video_id}] Removing partial download: {part_file.name}")
        part_file.unlink()

    # Skip if already downloaded locally (exclude .part files), but validate audio
    import re as _re
    all_existing = [f for f in sorted(run_dir.glob("video.*")) if not f.name.endswith(".part")]
    existing = [f for f in all_existing if not _re.search(r"\.f\d+\.", f.name)] or all_existing
    if existing:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(existing[0])],
            capture_output=True, text=True, timeout=30,
        )
        if probe.stdout.strip():
            print(f"  [{video_id}] Video already exists locally with audio, skipping download")
        else:
            print(f"  [{video_id}] Cached file has no audio stream, re-downloading...")
            existing[0].unlink()
            download_video(video_id, run_dir)
            print(f"  [{video_id}] Download complete")
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
                    sentry_sdk.capture_exception()
                    traceback.print_exc()
                    db.mark_video_failed(video["id"], f"Download failed: {traceback.format_exc()}")
                    print(f"  [{vid}] FAILED")
        except Exception:
            sentry_sdk.capture_exception()
            traceback.print_exc()
        time.sleep(poll_interval)
