# Workers & Database Architecture

## Overview

The system has two halves that share a Supabase Postgres database:

1. **Web app** (Next.js) — user-facing frontend + API routes. Handles auth, video conversion requests, subscription management.
2. **Worker process** (Python) — four daemon threads polling the database and doing background work.

The web app writes to the database (creates users, videos, subscriptions, deliveries). The workers read from the database, do work (download, process, discover, deliver), and update rows when done.

## Database Schema

### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | 12-char hex UUID |
| `email` | TEXT UNIQUE | |
| `workos_user_id` | TEXT UNIQUE | WorkOS auth identity |
| `created_at` | TIMESTAMPTZ | |

Created by the web app on first login via WorkOS.

### `channels`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `youtube_channel_id` | TEXT UNIQUE | e.g. `UCxxxxxx` |
| `name` | TEXT | Display name, updated from RSS feed title |
| `thumbnail_url` | TEXT | |
| `description` | TEXT | |
| `last_checked_at` | TIMESTAMPTZ | When discover worker last polled RSS |
| `created_at` | TIMESTAMPTZ | |

Created by the web app when a user subscribes to a channel. The discover worker updates `last_checked_at` and `name`.

### `videos`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `youtube_video_id` | TEXT UNIQUE | e.g. `dQw4w9WgXcQ` |
| `youtube_url` | TEXT | Full watch URL |
| `video_title` | TEXT | Set by download worker from yt-dlp metadata |
| `channel_id` | TEXT FK→channels | NULL for one-off conversions |
| `downloaded_at` | TIMESTAMPTZ | Set by download worker |
| `processed_at` | TIMESTAMPTZ | Set by process worker |
| `error` | TEXT | Set on permanent failure |
| `created_at` | TIMESTAMPTZ | |

**Two creation paths:**
- **One-off:** web app creates the row when a user pastes a URL (no `channel_id`).
- **Subscription:** discover worker creates the row when it finds a new video in a channel's RSS feed (has `channel_id`).

**State machine:**
```
created (downloaded_at=NULL, processed_at=NULL, error=NULL)
  → downloaded (downloaded_at set)
  → processed (processed_at set)
  → failed (error set) — terminal, no retries
```

### `subscriptions`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `user_id` | TEXT FK→users | |
| `channel_id` | TEXT FK→channels | |
| `poll_interval_hours` | INTEGER | Default 1. Controls how often discover worker checks the channel RSS. |
| `active` | BOOLEAN | Soft delete — deactivated subs are ignored |
| `created_at` | TIMESTAMPTZ | |
| | UNIQUE | `(user_id, channel_id)` |

Created/deactivated by the web app.

### `deliveries`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `video_id` | TEXT FK→videos | |
| `user_id` | TEXT FK→users | |
| `source` | TEXT | `'one_off'` or `'subscription'` |
| `subscription_id` | TEXT FK→subscriptions | Only set for subscription deliveries |
| `sent_at` | TIMESTAMPTZ | Set by deliver worker on successful send |
| `error` | TEXT | Set on permanent failure |
| `created_at` | TIMESTAMPTZ | |
| | UNIQUE | `(video_id, user_id)` — prevents duplicate emails |

**Two creation paths:**
- **One-off:** web app creates the row when a user clicks convert (`source='one_off'`).
- **Subscription:** deliver worker bulk-creates rows for processed subscription videos that don't have a delivery yet (`source='subscription'`).

**State machine:**
```
pending (sent_at=NULL, error=NULL)
  → sent (sent_at set)
  → failed (error set) — terminal, no retries
```

## Entity Relationships

```
users 1──* subscriptions *──1 channels
users 1──* deliveries    *──1 videos *──1 channels
```

- A user can subscribe to many channels. A channel can have many subscribers.
- A user can have many deliveries. A video can have many deliveries (one per user).
- A video optionally belongs to a channel (NULL for one-off conversions).
- The `UNIQUE(video_id, user_id)` on deliveries ensures each user gets at most one email per video.

## Workers

All four workers run as daemon threads in a single Python process, started by `worker.py:start_worker_threads()`. Each worker is an infinite loop that polls the database at a fixed interval.

### 1. Discover Worker (`discover_worker.py`)

**Poll interval:** 60s

**Purpose:** Find new videos on subscribed YouTube channels.

**Behavior:**
1. Query `get_channels_due_for_check()` — returns channels where at least one active subscriber's `poll_interval_hours` has elapsed since `last_checked_at`.
2. For each channel, fetch the YouTube RSS feed (`/feeds/videos.xml?channel_id=...`).
3. Parse entries. Skip videos published before the channel's `last_checked_at` (or `created_at` on first check — prevents backfilling the entire feed).
4. For each new video not already in the DB, insert a `videos` row with `channel_id` set.
5. Update `channels.last_checked_at`.

**Writes:** `videos` (INSERT), `channels` (UPDATE `last_checked_at`, `name`).

### 2. Download Worker (`download_worker.py`)

**Poll interval:** 10s

**Purpose:** Download video files and metadata from YouTube.

**Behavior:**
1. Query `get_videos_pending_download()` — returns videos where `downloaded_at IS NULL AND error IS NULL`.
2. For each video, download via yt-dlp to `runs/<youtube_video_id>/00_download/`.
3. Fetch metadata via `yt-dlp --dump-json`, save to `metadata.json`.
4. Set `downloaded_at` and `video_title` on the video row.
5. On failure, set `error` — no retries.

**Writes:** `videos` (UPDATE `downloaded_at`, `video_title`, or `error`). Files to disk.

### 3. Process Worker (`process_worker.py`)

**Poll interval:** 10s

**Purpose:** Run the full essay pipeline on downloaded videos.

**Behavior:**
1. Query `get_videos_pending_processing()` — returns videos where `downloaded_at IS NOT NULL AND processed_at IS NULL AND error IS NULL`.
2. For each video, run the pipeline steps in order:
   - **Transcript:** Extract audio → Deepgram API → speaker mapping → formatted transcript.
   - **Filter sponsors:** Claude Haiku detects ad segments → cleaned transcript.
   - **Essay:** Claude Sonnet generates essay from cleaned transcript.
   - **Extract frames:** Sample frames from video → dedup → classify with Haiku → filter.
   - **Place images:** Sonnet places frames into essay → annotate figures → embed base64.
3. Set `processed_at` on the video row.
4. On failure, set `error` — no retries.

**Writes:** `videos` (UPDATE `processed_at` or `error`). Files to disk under `runs/<youtube_video_id>/01_transcript/` through `05_place_images/`.

**Requires:** `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`.

### 4. Deliver Worker (`deliver_worker.py`)

**Poll interval:** 15s

**Purpose:** Send essay emails to users via AgentMail.

**Behavior (two phases per cycle):**

**Phase 1 — Create subscription deliveries:**
1. Run `create_subscription_deliveries()` — a single SQL INSERT...SELECT that finds all (subscriber, processed video) pairs with no delivery row and bulk-creates them with `source='subscription'`.

**Phase 2 — Send pending deliveries:**
1. Query `get_pending_deliveries()` — returns all delivery rows where `sent_at IS NULL AND error IS NULL` and the video is processed.
2. For each delivery, read the essay from disk (prefer `essay_final.md`, fall back to `essay.md`).
3. Send email via `send_essay()` (AgentMail API).
4. On success, set `sent_at`.
5. On failure (essay not found or send error), set `error` — no retries.

**Writes:** `deliveries` (INSERT for subscriptions, UPDATE `sent_at` or `error`).

**Requires:** `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`.

## Data Flow

### One-off conversion (user pastes a URL)

```
Web app                          Workers
───────                          ───────
POST /api/videos
  → create video row
  → create delivery row ──────→ download worker picks up video
    (source='one_off')             → downloads video + metadata
                                   → sets downloaded_at
                                 process worker picks up video
                                   → runs pipeline
                                   → sets processed_at
                                 deliver worker picks up delivery
                                   → reads essay from disk
                                   → sends email
                                   → sets sent_at
```

### Subscription (new video on a subscribed channel)

```
Web app                          Workers
───────                          ───────
POST /api/subscriptions
  → create channel row
  → create subscription row ──→ discover worker checks RSS
                                   → finds new video
                                   → creates video row (with channel_id)
                                 download worker picks up video
                                   → downloads video + metadata
                                 process worker picks up video
                                   → runs pipeline
                                 deliver worker creates delivery row
                                   → reads essay from disk
                                   → sends email
                                   → sets sent_at
```

## File Layout on Disk

Each video's artifacts are stored under `runs/<youtube_video_id>/`:

```
runs/<youtube_video_id>/
  00_download/      ← download worker
    video.mp4
    metadata.json
  01_transcript/    ← process worker
    audio.mp3
    transcript.txt
    diarization.json
    deepgram_response.json
    speaker_map.json (multi-speaker only)
  02_filter_sponsors/
    transcript_clean.txt
    sponsor_segments.json
  03_essay/
    essay.md
  04_frames/
    raw/
    kept/
    classifications.json
  05_place_images/
    essay_final.md
```
