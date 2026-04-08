"""Download worker: downloads videos via yt-dlp, uploads to S3, marks as downloaded."""

import json
import logging
import os
import subprocess
import time
import traceback
from pathlib import Path

import sentry_sdk

from . import db
from .s3 import upload_run
from .transcriber import download_video, fetch_video_metadata

logger = logging.getLogger(__name__)

RUNS_DIR = Path("runs")


def _download_one(video: dict) -> None:
    """Download a single video locally."""
    video_id = video["youtube_video_id"]
    run_dir = RUNS_DIR / video_id / "00_download"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Clean up partial downloads
    for part_file in run_dir.glob("video.*.part"):
        logger.info("[%s] Removing partial download: %s", video_id, part_file.name)
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
            logger.info("[%s] Video already exists locally with audio, skipping download", video_id)
        else:
            logger.info("[%s] Cached file has no audio stream, re-downloading...", video_id)
            existing[0].unlink()
            download_video(video_id, run_dir)
            logger.info("[%s] Download complete", video_id)
    else:
        logger.info("[%s] Downloading video...", video_id)
        download_video(video_id, run_dir)
        logger.info("[%s] Download complete", video_id)

    # Save metadata
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        logger.info("[%s] Fetching metadata...", video_id)
        meta: dict = {"url": video["youtube_url"], "video_id": video_id}
        try:
            yt_meta = fetch_video_metadata(video_id)
            meta.update(yt_meta)
        except Exception as e:
            logger.warning("[%s] Metadata fetch failed: %s", video_id, e)
        meta_path.write_text(json.dumps(meta, indent=2))

    # Get title from metadata
    title = video.get("video_title")
    if not title and meta_path.exists():
        meta_data = json.loads(meta_path.read_text())
        title = meta_data.get("title")

    logger.info("[%s] Uploading to S3...", video_id)
    upload_run(video_id, step_dirs=["00_download"])
    db.mark_video_downloaded(video["id"], video_title=title)
    logger.info("[%s] Done (%s)", video_id, title or "untitled")


def download_loop(poll_interval: float = 10.0) -> None:
    """Poll for videos pending download and process them."""
    from .worker import init_sentry
    init_sentry()
    logger.info("Download worker started (polling every %ss)", poll_interval)
    for key in ("DATABASE_URL", "S3_BUCKET_NAME", "PROXY_URL"):
        val = os.environ.get(key)
        logger.info("  %s: %s", key, "set" if val else "NOT SET")
    while True:
        try:
            logger.debug("Polling...")
            videos = db.get_videos_pending_download()
            if videos:
                logger.info("Found %d video(s) pending download", len(videos))
            for video in videos:
                vid = video["youtube_video_id"]
                logger.info("[%s] Starting download for %s", vid, video.get("youtube_url", vid))
                try:
                    _download_one(video)
                except Exception:
                    sentry_sdk.capture_exception()
                    logger.exception("[%s] Download failed", vid)
                    db.mark_video_failed(video["id"], f"Download failed: {traceback.format_exc()}")
        except Exception:
            sentry_sdk.capture_exception()
            logger.exception("Download worker: error in poll loop")
        time.sleep(poll_interval)
