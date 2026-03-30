"""Discover worker: polls YouTube RSS feeds for new videos on subscribed channels."""

import os
import traceback
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from . import db

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"


def _check_channel(channel: dict) -> int:
    """Fetch RSS feed for a channel and insert any new videos. Returns count of new videos."""
    youtube_channel_id = channel["youtube_channel_id"]
    url = YOUTUBE_RSS_URL.format(channel_id=youtube_channel_id)

    proxy_url = os.environ.get("PROXY_URL")
    with httpx.Client(proxy=proxy_url, timeout=30) as client:
        resp = client.get(url)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)

    # Update channel name from feed title if it's still a placeholder
    feed_title = root.findtext(f"{ATOM_NS}title")
    if feed_title and channel["name"] == youtube_channel_id:
        db.update_channel_name(channel["id"], feed_title)

    # Only add videos published after the channel was added to our system.
    # On first check (last_checked_at is None), use created_at as the cutoff
    # so we don't backfill the entire RSS feed.
    cutoff = channel.get("last_checked_at") or channel["created_at"]
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    new_count = 0
    for entry in root.findall(f"{ATOM_NS}entry"):
        video_id = entry.findtext(f"{YT_NS}videoId")
        if not video_id:
            continue

        # Skip videos published before we started tracking this channel
        published_str = entry.findtext(f"{ATOM_NS}published")
        if published_str:
            published = datetime.fromisoformat(published_str)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published <= cutoff:
                continue

        # Check if we already have this video
        existing = db.get_video_by_youtube_id(video_id)
        if existing:
            continue

        title = entry.findtext(f"{ATOM_NS}title")
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        db.create_video(
            youtube_video_id=video_id,
            youtube_url=video_url,
            channel_id=channel["id"],
            video_title=title,
        )
        new_count += 1

    db.update_channel_checked(channel["id"])
    return new_count


def discover_loop(poll_interval: float = 60.0) -> None:
    """Poll for channels due for a check and discover new videos."""
    print(f"Discover worker started (polling every {poll_interval}s)")
    for key in ("DATABASE_URL", "PROXY_URL"):
        val = os.environ.get(key)
        print(f"  {key}: {'set' if val else 'NOT SET'}")
    while True:
        try:
            channels = db.get_channels_due_for_check()
            for channel in channels:
                try:
                    new = _check_channel(channel)
                    if new:
                        print(f"Discover: {new} new video(s) from {channel['name']}")
                except Exception:
                    traceback.print_exc()
                    print(f"Discover: error checking channel {channel.get('name', channel['id'])}")
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
