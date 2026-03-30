"""Discover worker: polls YouTube Data API for new videos on subscribed channels."""

import os
import traceback
import time
from datetime import datetime, timezone

import httpx

from . import db

PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


def _uploads_playlist_id(channel_id: str) -> str:
    """Convert a channel ID (UC...) to its uploads playlist ID (UU...)."""
    return "UU" + channel_id[2:]


def _check_channel(channel: dict, api_key: str) -> int:
    """Fetch uploads playlist for a channel and insert any new videos. Returns count of new videos."""
    youtube_channel_id = channel["youtube_channel_id"]
    playlist_id = _uploads_playlist_id(youtube_channel_id)

    cutoff = channel.get("last_checked_at") or channel["created_at"]
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    new_count = 0
    page_token: str | None = None

    while True:
        params: dict = {
            "playlistId": playlist_id,
            "part": "snippet",
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = httpx.get(PLAYLIST_ITEMS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Update channel name from first result if still a placeholder
        if channel["name"] == youtube_channel_id and data.get("items"):
            channel_title = data["items"][0]["snippet"].get("channelTitle")
            if channel_title:
                db.update_channel_name(channel["id"], channel_title)

        found_old = False
        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]

            published = datetime.fromisoformat(snippet["publishedAt"])
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published <= cutoff:
                found_old = True
                break

            existing = db.get_video_by_youtube_id(video_id)
            if existing:
                continue

            title = snippet.get("title")
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            db.create_video(
                youtube_video_id=video_id,
                youtube_url=video_url,
                channel_id=channel["id"],
                video_title=title,
            )
            new_count += 1

        # Stop paginating if we hit old videos or there are no more pages
        if found_old or "nextPageToken" not in data:
            break
        page_token = data["nextPageToken"]

    db.update_channel_checked(channel["id"])
    return new_count


def discover_loop(poll_interval: float = 60.0) -> None:
    """Poll for channels due for a check and discover new videos."""
    print(f"Discover worker started (polling every {poll_interval}s)")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  YOUTUBE_API_KEY: NOT SET — discover worker cannot run")
        return
    for key in ("DATABASE_URL", "YOUTUBE_API_KEY"):
        val = os.environ.get(key)
        print(f"  {key}: {'set' if val else 'NOT SET'}")
    while True:
        try:
            channels = db.get_channels_due_for_check()
            for channel in channels:
                try:
                    new = _check_channel(channel, api_key)
                    if new:
                        print(f"Discover: {new} new video(s) from {channel['name']}")
                except Exception:
                    traceback.print_exc()
                    print(f"Discover: error checking channel {channel.get('name', channel['id'])}")
        except Exception:
            traceback.print_exc()
        time.sleep(poll_interval)
