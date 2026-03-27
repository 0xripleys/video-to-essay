"""Deliver worker: sends essay emails for processed videos."""

import traceback
import time
from pathlib import Path

from . import db
from .email_sender import send_essay

RUNS_DIR = Path("runs")


def _get_essay(youtube_video_id: str) -> str | None:
    """Read the final essay from disk (S3 integration later)."""
    essay_path = RUNS_DIR / youtube_video_id / "05_place_images" / "essay_final.md"
    if essay_path.exists():
        return essay_path.read_text()
    # Fall back to plain essay without images
    essay_path = RUNS_DIR / youtube_video_id / "03_essay" / "essay.md"
    if essay_path.exists():
        return essay_path.read_text()
    return None


def _deliver_one_offs() -> None:
    """Send emails for one-off deliveries."""
    deliveries = db.get_pending_one_off_deliveries()
    for d in deliveries:
        try:
            essay = _get_essay(d["youtube_video_id"])
            if not essay:
                db.mark_delivery_failed(d["id"], "Essay file not found")
                continue

            title = d.get("video_title") or "Untitled Video"
            send_essay(d["email"], title, essay)
            db.mark_delivery_sent(d["id"])
            print(f"Deliver: sent to {d['email']} ({title})")
        except Exception:
            traceback.print_exc()
            db.mark_delivery_failed(d["id"], traceback.format_exc())
            print(f"Deliver: failed sending to {d['email']}")


def _deliver_subscriptions() -> None:
    """Send emails for subscription deliveries (computed at delivery time)."""
    pending = db.get_pending_subscription_deliveries()
    for p in pending:
        try:
            essay = _get_essay(p["youtube_video_id"])
            if not essay:
                continue  # Video processed but essay not on disk yet — retry later

            title = p.get("video_title") or "Untitled Video"

            # Create delivery record (dedup via unique constraint)
            delivery_id = db.create_delivery(
                video_id=p["video_id"],
                user_id=p["user_id"],
                source="subscription",
                subscription_id=p.get("subscription_id"),
            )
            if delivery_id is None:
                continue  # Already delivered

            send_essay(p["email"], title, essay)
            db.mark_delivery_sent(delivery_id)
            print(f"Deliver: sent subscription essay to {p['email']} ({title})")
        except Exception:
            traceback.print_exc()
            print(f"Deliver: failed sending subscription essay to {p.get('email')}")


def deliver_loop(poll_interval: float = 15.0) -> None:
    """Poll for pending deliveries and send emails."""
    print(f"Deliver worker started (polling every {poll_interval}s)")
    while True:
        try:
            _deliver_one_offs()
            _deliver_subscriptions()
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
