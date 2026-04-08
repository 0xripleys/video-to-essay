# Filter Shorts and Live Streams

## Problem

Channels like @notthreadguy publish a mix of regular videos, live streams, and shorts. Users receive essays for all of them, but shorts produce poor essays (too little content) and some users don't want live stream essays. There's currently no way to filter by video type.

## Requirements

- **Shorts**: Always filtered out globally. No user setting. Videos with duration ≤ 60s are never inserted into the `videos` table.
- **Live streams**: Included by default. Per-subscription toggle to exclude. Presented as a synthetic "Live Streams" playlist in the playlist picker UI.

## Database Changes

### `videos` table

Add column:

```sql
ALTER TABLE videos ADD COLUMN IF NOT EXISTS is_livestream BOOLEAN NOT NULL DEFAULT FALSE;
```

Set during discovery based on the presence of `liveStreamingDetails` from the YouTube Data API `videos.list` response.

### `subscriptions` table

Add column:

```sql
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS exclude_livestreams BOOLEAN NOT NULL DEFAULT FALSE;
```

Default `FALSE` = live streams are included (matching current behavior).

## Discover Worker Changes (`discover_worker.py`)

### Rename and extend `_filter_active_livestreams`

Rename to `_classify_videos`. Add `contentDetails` to the existing `part` parameter (currently only `liveStreamingDetails`). No additional API calls — just more data from the same request.

Returns a dict per video with:
- `is_active_stream`: `liveStreamingDetails` present but no `actualEndTime`
- `is_livestream`: `liveStreamingDetails` present (regardless of end time)
- `is_short`: `contentDetails.duration` parses to ≤ 60 seconds

### Filtering logic in `_check_channel`

For each candidate video after classification:

1. **Active/upcoming streams**: Skip (existing behavior).
2. **Shorts** (duration ≤ 60s): Skip unconditionally. Never insert.
3. **Completed live streams**: Check all active subscriptions for the channel. If every subscription has `exclude_livestreams = TRUE`, skip the video entirely (avoids downloading/processing unwanted content). Otherwise, insert with `is_livestream = TRUE`.
4. **Regular videos**: Insert as before.

## Delivery Filtering (`db.py`)

In `create_subscription_deliveries()`, add a condition to the WHERE clause:

```sql
AND (s.exclude_livestreams = FALSE OR v.is_livestream = FALSE)
```

This prevents delivery rows from being created for live stream videos when the subscription excludes them. Handles the case where a video was inserted because at least one subscriber wanted it, but other subscribers on the same channel have excluded live streams.

## API Changes

### `POST /api/channels` (subscribe)

Accept optional `exclude_livestreams: boolean` in the request body. Pass through to `createSubscription()`.

### `PATCH /api/subscriptions/[subId]` (update settings)

Accept optional `exclude_livestreams: boolean` in the request body. Update the subscription row.

### `createSubscription()` in `db.ts`

Add `excludeLivestreams` parameter. Include in the INSERT/upsert query.

## UI Changes

### Synthetic "Live Streams" playlist entry

In both `AddChannelModal.tsx` (Phase 3 — playlist picker) and `EditPlaylistsModal` (in `ChannelsPage.tsx`), inject a synthetic playlist entry:

- **Label**: "Live Streams"
- **Position**: At the top of the playlist list, visually identical to real playlists
- **Default state**: Checked (live streams included)
- **Behavior**: Unchecking sends `exclude_livestreams: true` to the API. Checking sends `exclude_livestreams: false`.

This entry only appears when the user selects "Specific playlists" mode. When "All uploads" is selected, live streams are included regardless (the `exclude_livestreams` flag is set to `false`).

When editing an existing subscription, the checkbox reflects the current `exclude_livestreams` value from the subscription row.

## Shorts Detection: Duration Heuristic

YouTube Shorts are identified by duration ≤ 60 seconds, parsed from `contentDetails.duration` (ISO 8601 format, e.g., `PT45S`). This heuristic is ~95% accurate:

- **False positives**: Some regular short clips (trailers, teasers) may be filtered out. Acceptable — these rarely produce good essays anyway.
- **False negatives**: Shorts up to 3 minutes exist on some channels, but are rare.

No official YouTube API field identifies Shorts. The duration heuristic is the most reliable approach that uses official API data and requires no extra API calls.
