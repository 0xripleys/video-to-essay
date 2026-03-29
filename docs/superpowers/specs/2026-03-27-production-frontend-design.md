# Production Frontend Design

## Overview

Upgrade the video-to-essay web app from a proof-of-concept (two pages, no auth) to a production-ready application with authentication, an in-browser essay reader, channel subscriptions with automatic new-video detection, and email delivery.

## Auth

WorkOS AuthKit with Magic Auth (6-digit email codes sent to user's email).

- On first login, create a `users` record keyed by WorkOS user ID
- Session managed via WorkOS tokens in HTTP-only cookies
- All API routes except `/api/health` require a valid session; frontend redirects to AuthKit login on 401
- Google/Microsoft OAuth can be toggled on later in the WorkOS dashboard with no code changes

## Data Model

### Entity Tables

**`users`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `email` | TEXT UNIQUE | |
| `workos_user_id` | TEXT UNIQUE | |
| `created_at` | TEXT | ISO 8601 |

**`videos`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `youtube_video_id` | TEXT UNIQUE | |
| `youtube_url` | TEXT | |
| `video_title` | TEXT NULL | Set after download/metadata fetch |
| `channel_id` | TEXT NULL FK | NULL for one-off submissions |
| `downloaded_at` | TEXT NULL | Set by download worker |
| `processed_at` | TEXT NULL | Set by pipeline worker |
| `error` | TEXT NULL | Set on failure |
| `created_at` | TEXT | ISO 8601 |

**`channels`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `youtube_channel_id` | TEXT UNIQUE | |
| `name` | TEXT | |
| `last_checked_at` | TEXT NULL | |
| `created_at` | TEXT | ISO 8601 |

**`subscriptions`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `user_id` | TEXT FK | |
| `channel_id` | TEXT FK | |
| `poll_interval_hours` | INTEGER | Default 1 |
| `active` | BOOLEAN | |
| `created_at` | TEXT | ISO 8601 |

### Delivery Log

**`deliveries`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | |
| `video_id` | TEXT FK | |
| `user_id` | TEXT FK | |
| `source` | TEXT | `one_off` or `subscription` |
| `subscription_id` | TEXT NULL FK | NULL for one-off |
| `sent_at` | TEXT NULL | Set after email sent |
| `error` | TEXT NULL | |
| `created_at` | TEXT | ISO 8601 |

**Unique constraint** on `(video_id, user_id)` to prevent duplicate deliveries.

`deliveries` serves as a sent log. For subscription videos, the deliver worker computes recipients at delivery time by joining `videos.channel_id` to `subscriptions`, then checks `deliveries` to skip already-sent. For one-off submissions, a delivery row is created at submission time with `sent_at=NULL`.

## S3 Convention

All artifacts for a video live under: `youtube/<youtube_video_id>/`

Contents: `video.mp4`, `audio.mp3`, `transcript.txt`, `essay.md`, `essay_final.md`, `frames/`, etc.

The path is deterministic from the video ID — not stored in the database.

Future platforms (e.g., Spotify) would use `spotify/<episode_id>/`.

## Workers

Four independent workers, each with one job:

### Discover Worker

- Runs on a loop
- For each channel where `now - last_checked_at > shortest subscriber poll_interval_hours`: fetch YouTube RSS feed (`https://www.youtube.com/feeds/videos.xml?channel_id=...`)
- Compare video IDs against existing `videos` rows
- For new videos: insert into `videos` (with `channel_id`)
- Update `channels.last_checked_at`
- Does NOT create delivery rows — the deliver worker handles that

### Download Worker (future — runs on residential proxy)

- Query: `SELECT FROM videos WHERE downloaded_at IS NULL AND error IS NULL`
- Downloads video, uploads to S3 at `youtube/<youtube_video_id>/`
- Sets `videos.downloaded_at` on success
- Sets `videos.error` on failure

Not built now. The job queue interface is defined so it can be plugged in later. For development/testing, this step can be run locally.

### Process Worker

- Query: `SELECT FROM videos WHERE downloaded_at IS NOT NULL AND processed_at IS NULL AND error IS NULL`
- Pulls video from S3
- Runs: transcript (Deepgram) -> filter sponsors -> essay -> extract frames -> place images
- Uploads artifacts to S3 under `youtube/<youtube_video_id>/`
- Sets `videos.processed_at` on success
- Sets `videos.error` on failure

### Deliver Worker

- For one-offs: `SELECT FROM deliveries WHERE sent_at IS NULL` joined with `videos WHERE processed_at IS NOT NULL`
- For subscriptions: find processed videos with a `channel_id`, join to `subscriptions` to find subscribers, check `deliveries` to skip already-sent
- Sends essay email via AgentMail
- Inserts/updates `deliveries` row with `sent_at`

### Worker Properties

- All workers are idempotent: if they crash, timestamps stay NULL and they retry next loop
- Workers poll on configurable intervals (e.g., 5-30 seconds for download/process/deliver, configurable for discover per channel)
- Each worker only reads its own inputs and writes to `videos` + its own outputs

## API Endpoints

All endpoints except health and auth require a valid WorkOS session.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `*` | `/api/auth/*` | WorkOS auth flow (login, callback, logout) |
| `POST` | `/api/videos` | One-off submission: creates `videos` + `deliveries` row |
| `GET` | `/api/videos` | List user's videos (via deliveries + subscriptions) |
| `GET` | `/api/videos/{id}` | Video status + essay content (fetched from S3) |
| `POST` | `/api/channels` | Subscribe to a channel (creates `channels` + `subscriptions`) |
| `GET` | `/api/channels` | List user's subscriptions |
| `DELETE` | `/api/subscriptions/{id}` | Unsubscribe (sets `active=false`) |

### Video Status Derivation

Status is derived from `videos` timestamps rather than stored explicitly:

- `downloaded_at` is NULL -> `downloading`
- `processed_at` is NULL -> `processing` (with `current_step` if available)
- `processed_at` is set -> `done`
- `error` is set -> `failed`

For the current user, also check `deliveries` to show if email was sent.

## Frontend

### Tech Stack

- Next.js (static export) + Tailwind CSS
- Served by FastAPI as static files
- Client-side rendering, all data fetching via API calls
- Plain React hooks for state (useState, useEffect)

### Layout

Persistent sidebar on every page:

- App name ("Surat")
- Nav links: Videos (dashboard), Subscriptions, Settings
- Subscribed channels list with "+ Add channel" shortcut

### Pages

#### Login

WorkOS AuthKit hosted login. Redirects to dashboard on success.

#### Dashboard (Videos) — `/`

- URL input bar at top for one-off submissions
- Below: list of all user's videos (from subscriptions + one-offs)
- Each row shows: video title, channel name or "One-off", relative date, status indicator
- Status indicators:
  - Pulsing amber dot + current step name (downloading, transcript, essay, etc.)
  - Green "Ready" with arrow (click to open essay reader)
  - Red "Failed"
- Polls API for status updates on in-progress videos

#### Essay Reader — `/videos/{id}`

- Sidebar stays visible
- "Back to Videos" link at top
- Metadata: channel name, date, "Watch on YouTube" link
- Rendered essay in Georgia serif font with images and figure annotations
- Essay HTML fetched from S3 via the API

#### Subscriptions — `/subscriptions`

- List of tracked channels
- Per channel: name, poll interval dropdown, unsubscribe button, recent videos
- "+ Add channel" input at top (accepts channel URL or video URL — extracts channel)

#### Settings — `/settings`

- Email preferences
- Default poll interval
- Account info (email, logout)

## What's NOT In Scope

- Download worker implementation (future, needs residential proxy)
- Rate limiting and abuse prevention
- Multi-platform support (Spotify, etc.) — just the S3 prefix convention
- Mobile-specific layouts
- Search or filtering of videos
- Public/shared essay pages
