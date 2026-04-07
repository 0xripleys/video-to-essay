"""Deliver worker: sends essay emails for processed videos."""

import logging
import os
import time

import sentry_sdk

from . import db
from .email_sender import send_essay
from .s3 import download_file

logger = logging.getLogger(__name__)


def _get_essay(youtube_video_id: str) -> str | None:
    """Read the final essay from S3."""
    for path in ("05_place_images/essay_final.md", "03_essay/essay.md"):
        try:
            return download_file(youtube_video_id, path).decode()
        except Exception:
            continue
    return None


def _deliver() -> None:
    """Send emails for all pending deliveries."""
    deliveries = db.get_pending_deliveries()
    if deliveries:
        logger.info("Found %d pending deliveries", len(deliveries))
    for d in deliveries:
        did, email, vid = d["id"], d["email"], d["youtube_video_id"]
        try:
            essay = _get_essay(vid)
            if not essay:
                logger.warning("delivery=%s: essay not found for video %s, marking failed", did, vid)
                db.mark_delivery_failed(did, "Essay file not found")
                continue

            title = d.get("video_title") or "Untitled Video"
            channel_name = d.get("channel_name")
            logger.info("delivery=%s: sending to %s (%s)", did, email, title)
            send_essay(email, title, essay, channel_name=channel_name)
            db.mark_delivery_sent(did)
            logger.info("delivery=%s: sent successfully", did)
        except Exception:
            logger.exception("delivery=%s: failed sending to %s", did, email)
            db.mark_delivery_failed(did, "Send failed")


def deliver_loop(poll_interval: float = 15.0) -> None:
    """Poll for pending deliveries and send emails."""
    logger.info("Deliver worker started (polling every %.1fs)", poll_interval)
    for key in ("DATABASE_URL", "AGENTMAIL_API_KEY", "AGENTMAIL_INBOX_ID", "S3_BUCKET_NAME"):
        val = os.environ.get(key)
        logger.info("  %s: %s", key, "set" if val else "NOT SET")
    while True:
        try:
            created = db.create_subscription_deliveries()
            if created:
                logger.info("Created %d subscription deliveries", created)
            _deliver()
        except Exception:
            sentry_sdk.capture_exception()
            logger.exception("Unexpected error in deliver loop")
        time.sleep(poll_interval)
