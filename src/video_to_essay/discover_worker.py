"""Discover worker: polls YouTube Data API for new videos on subscribed channels."""

import os
import traceback
import time
from datetime import datetime, timezone

import httpx

from . import db

PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _uploads_playlist_id(channel_id: str) -> str:
    """Convert a channel ID (UC...) to its uploads playlist ID (UU...)."""
    return "UU" + channel_id[2:]


def _video_in_playlist(video_id: str, playlist_id: str, api_key: str) -> bool:
    """Check if a video exists in a YouTube playlist."""
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
        for item in data.get("items", []):
            if item["snippet"]["resourceId"]["videoId"] == video_id:
                return True
        if "nextPageToken" not in data:
            break
        page_token = data["nextPageToken"]
    return False


def _check_playlist_membership(
    video_id: str, channel_id: str, api_key: str
) -> list[str] | None:
    """Check whether a new video should be inserted based on subscription playlist filters.

    Returns None if any subscription is unfiltered (insert without restriction).
    Returns a list of matched playlist IDs if all subscriptions are filtered.
    Returns an empty list if the video matches no playlists (skip it).
    """
    subs = db.get_channel_subscriptions(channel_id)
    if not subs:
        return []  # no subscribers at all — skip

    # If any subscription wants all uploads, no filtering needed
    if any(s["playlist_ids"] is None for s in subs):
        return None

    # All subscriptions are filtered — collect unique playlist IDs
    all_playlist_ids: set[str] = set()
    for s in subs:
        all_playlist_ids.update(s["playlist_ids"])

    matched: list[str] = []
    for pl_id in all_playlist_ids:
        if _video_in_playlist(video_id, pl_id, api_key):
            matched.append(pl_id)

    return matched


def _filter_active_livestreams(video_ids: list[str], api_key: str) -> set[str]:
    """Return the set of video IDs that are upcoming or currently live (not yet downloadable)."""
    active = set()
    # videos.list accepts up to 50 IDs per request
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = httpx.get(
            VIDEOS_URL,
            params={
                "id": ",".join(batch),
                "part": "liveStreamingDetails",
                "key": api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            details = item.get("liveStreamingDetails")
            if details and "actualEndTime" not in details:
                active.add(item["id"])
    return active


def _check_channel(channel: dict, api_key: str) -> int:
    """Fetch uploads playlist for a channel and insert any new videos. Returns count of new videos."""
    youtube_channel_id = channel["youtube_channel_id"]
    playlist_id = _uploads_playlist_id(youtube_channel_id)

    cutoff = channel.get("last_checked_at") or channel["created_at"]
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    # Collect candidate videos first, then filter and insert
    candidates: list[dict] = []
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

            # Check playlist filtering
            membership = _check_playlist_membership(video_id, channel["id"], api_key)
            if membership is not None and len(membership) == 0:
                continue  # no subscriber wants this video

            candidates.append({
                "video_id": video_id,
                "title": snippet.get("title"),
                "membership": membership,
            })

        # Stop paginating if we hit old videos or there are no more pages
        if found_old or "nextPageToken" not in data:
            break
        page_token = data["nextPageToken"]

    # Filter out upcoming/active livestreams
    if candidates:
        active_streams = _filter_active_livestreams(
            [c["video_id"] for c in candidates], api_key
        )
        if active_streams:
            print(f"Discover: skipping {len(active_streams)} active/upcoming livestream(s)")
    else:
        active_streams = set()

    new_count = 0
    for c in candidates:
        if c["video_id"] in active_streams:
            continue
        video_url = f"https://www.youtube.com/watch?v={c['video_id']}"
        db.create_video(
            youtube_video_id=c["video_id"],
            youtube_url=video_url,
            channel_id=channel["id"],
            video_title=c["title"],
            matched_playlist_ids=c["membership"],
        )
        new_count += 1

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
