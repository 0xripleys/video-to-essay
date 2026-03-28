"""Download worker: downloads videos and marks them as downloaded.

This is a local dev stub. In production, this runs on a machine with
residential proxy access and uploads to S3. For now, it downloads locally
using yt-dlp and sets downloaded_at.
"""

import json
import os
import traceback
import time
from pathlib import Path

from . import db
from .transcriber import download_video, fetch_video_metadata

RUNS_DIR = Path("runs")


def _download_one(video: dict) -> None:
    """Download a single video locally."""
    video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / video_id / "00_download"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Skip if already downloaded locally
    existing = sorted(run_dir.glob("video.*"))
    if not existing:
        download_video(video_id, run_dir)

    # Save metadata
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        meta: dict = {"url": video["youtube_url"], "video_id": video_id}
        try:
            yt_meta = fetch_video_metadata(video_id)
            meta.update(yt_meta)
        except Exception:
            pass
        meta_path.write_text(json.dumps(meta, indent=2))

    # Get title from metadata
    title = video.get("video_title")
    if not title and meta_path.exists():
        meta_data = json.loads(meta_path.read_text())
        title = meta_data.get("title")

    db.mark_video_downloaded(video["id"], video_title=title)
    print(f"Download: completed {video_id} ({title or 'untitled'})")


def download_loop(poll_interval: float = 10.0) -> None:
    """Poll for videos pending download and process them."""
    print(f"Download worker started (polling every {poll_interval}s)")
    for key in ("DATABASE_URL",):
        val = os.environ.get(key)
        print(f"  {key}: {'set' if val else 'NOT SET'}")
    while True:
        try:
            videos = db.get_videos_pending_download()
            for video in videos:
                try:
                    _download_one(video)
                except Exception:
                    traceback.print_exc()
                    db.mark_video_failed(video["id"], f"Download failed: {traceback.format_exc()}")
                    print(f"Download: failed {video['youtube_video_id']}")
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
