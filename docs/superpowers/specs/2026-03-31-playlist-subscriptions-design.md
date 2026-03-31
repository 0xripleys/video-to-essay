# Playlist Subscriptions

## Goal

Allow users to subscribe to specific playlists within a channel instead of receiving all uploads. Avoid downloading videos that no subscriber wants.

## Schema Changes

### `subscriptions` table

Add column:
- `playlist_ids text[]` — nullable. When null, the subscription receives all uploads (current behavior). When set, only videos confirmed to be in one of these playlists are delivered.

### `videos` table

Add column:
- `matched_playlist_ids text[]` — nullable. Set by the discover worker when a video is confirmed to belong to specific playlists. Null for unfiltered discoveries and one-off conversions.

## Discover Worker

The uploads playlist is polled as today. The change is in what happens when a new video is found:

1. Poll the uploads playlist for a channel (no change).
2. New video found. Query all active subscriptions for this channel.
3. If any subscription has `playlist_ids IS NULL` (unfiltered), insert the video immediately. Set `matched_playlist_ids` to null.
4. If all subscriptions have `playlist_ids` set, collect the unique set of playlist IDs across all subscriptions. Call the YouTube Data API `playlistItems.list` for each playlist to check if the new video is a member. If the video is in at least one playlist, insert it with `matched_playlist_ids` set to the matching playlist IDs. If it matches none, skip the video entirely (no download, no processing).

API cost: step 4 only runs when all subscriptions are filtered AND a new upload is discovered. One API call per unique playlist ID per new video.

## Delivery Worker

`create_subscription_deliveries()` currently joins `videos → channels → subscriptions` and creates delivery rows for all processed videos. Add a filter:

```sql
WHERE s.playlist_ids IS NULL
   OR v.matched_playlist_ids && s.playlist_ids  -- PostgreSQL array overlap operator
```

This ensures:
- Unfiltered subscriptions receive all videos (no change).
- Filtered subscriptions only receive videos that matched their selected playlists.

## Web App

### Subscribe flow

The existing channel subscribe modal is extended:

1. User pastes a URL. Accept both channel URLs and playlist URLs.
2. **Channel URL** — resolve the channel, then fetch its playlists via a new API endpoint. Show a selection screen:
   - "All videos" radio option (default, sets `playlist_ids = null`)
   - List of the channel's playlists as checkboxes (each shows playlist name and video count)
3. **Playlist URL** — extract the playlist ID, resolve which channel it belongs to via YouTube API, then show the same selection screen with that playlist pre-selected.
4. Create the subscription with the chosen `playlist_ids` (null for all, or array of selected IDs).

### New API endpoint

`GET /api/channels/[channelId]/playlists` — calls YouTube Data API `playlists.list` with `channelId` param, returns playlist ID, name, thumbnail, and item count. Used by the subscribe flow to populate the playlist picker.

### Dashboard display

In the subscription list, show what each subscription is filtered to:
- `playlist_ids IS NULL` → "All videos"
- `playlist_ids` set → show playlist names (fetched at subscription creation time and stored, or resolved on display)

### URL parsing

Extend the existing URL parsing to handle:
- `youtube.com/playlist?list=PLxxxxxxx` — extract playlist ID
- `youtube.com/watch?v=xxx&list=PLxxxxxxx` — extract playlist ID from `list` param
- Existing channel URL formats continue to work

## What Does Not Change

- Download, process, and deliver workers' core logic remains the same.
- One-off video conversions are unaffected (no subscription, no playlist filtering).
- Channels with only unfiltered subscriptions behave exactly as today.
