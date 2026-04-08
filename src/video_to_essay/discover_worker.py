"""Discover worker: polls YouTube Data API for new videos on subscribed channels."""

import os
import traceback
import time
from datetime import datetime, timezone

import httpx
import sentry_sdk

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


def _parse_iso8601_duration(duration: str) -> int:
    """Parse an ISO 8601 duration (e.g. PT1H2M30S, PT45S) and return total seconds."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


class VideoClassification:
    __slots__ = ("is_active_stream", "is_livestream", "is_short")

    def __init__(self, is_active_stream: bool, is_livestream: bool, is_short: bool):
        self.is_active_stream = is_active_stream
        self.is_livestream = is_livestream
        self.is_short = is_short


def _classify_videos(video_ids: list[str], api_key: str) -> dict[str, VideoClassification]:
    """Classify videos as active streams, livestreams, or shorts using the YouTube Data API."""
    result: dict[str, VideoClassification] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = httpx.get(
            VIDEOS_URL,
            params={
                "id": ",".join(batch),
                "part": "liveStreamingDetails,contentDetails",
                "key": api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            vid = item["id"]
            live_details = item.get("liveStreamingDetails")
            duration_str = item.get("contentDetails", {}).get("duration", "")
            duration_secs = _parse_iso8601_duration(duration_str)
            result[vid] = VideoClassification(
                is_active_stream=bool(live_details and "actualEndTime" not in live_details),
                is_livestream=bool(live_details),
                is_short=duration_secs <= 60 and duration_secs > 0,
            )
    return result


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

    # Classify candidates (shorts, livestreams, active streams)
    if candidates:
        classifications = _classify_videos(
            [c["video_id"] for c in candidates], api_key
        )
    else:
        classifications = {}

    # Check if all subscriptions for this channel exclude livestreams
    subs = db.get_channel_subscriptions(channel["id"])
    all_exclude_livestreams = subs and all(s.get("exclude_livestreams", False) for s in subs)

    new_count = 0
    skipped_shorts = 0
    skipped_livestreams = 0
    for c in candidates:
        info = classifications.get(c["video_id"])
        if info and info.is_active_stream:
            continue
        if info and info.is_short:
            skipped_shorts += 1
            continue
        if info and info.is_livestream and all_exclude_livestreams:
            skipped_livestreams += 1
            continue
        video_url = f"https://www.youtube.com/watch?v={c['video_id']}"
        db.create_video(
            youtube_video_id=c["video_id"],
            youtube_url=video_url,
            channel_id=channel["id"],
            video_title=c["title"],
            matched_playlist_ids=c["membership"],
            is_livestream=bool(info and info.is_livestream),
        )
        new_count += 1

    if skipped_shorts:
        print(f"Discover: skipped {skipped_shorts} short(s)")
    if skipped_livestreams:
        print(f"Discover: skipped {skipped_livestreams} livestream(s) (all subscribers exclude)")

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
                    sentry_sdk.capture_exception()
                    traceback.print_exc()
                    print(f"Discover: error checking channel {channel.get('name', channel['id'])}")
        except Exception:
            sentry_sdk.capture_exception()
            traceback.print_exc()
        time.sleep(poll_interval)
