# Implementation Plan: Production Frontend

Based on: `docs/superpowers/specs/2026-03-27-production-frontend-design.md`

## Phase 1: Database

Rewrite `db.py` from scratch with the new schema. Delete the old `data/jobs.db` file — we're not in production.

### Steps

1. **Rewrite `src/video_to_essay/db.py`** with all tables:
   - `users` (id, email, workos_user_id, created_at)
   - `videos` (id, youtube_video_id, youtube_url, video_title, channel_id, downloaded_at, processed_at, error, created_at)
   - `channels` (id, youtube_channel_id, name, last_checked_at, created_at)
   - `subscriptions` (id, user_id, channel_id, poll_interval_hours, active, created_at)
   - `deliveries` (id, video_id, user_id, source, subscription_id, sent_at, error, created_at) with UNIQUE(video_id, user_id)
   - Helper functions: `create_user()`, `get_user_by_workos_id()`, `create_video()`, `get_video()`, `list_user_videos()`, `create_channel()`, `get_channel_by_youtube_id()`, `create_subscription()`, `list_user_subscriptions()`, `create_delivery()`, `get_pending_deliveries()`, etc.
   - Use WAL mode, same pattern as existing `db.py`

2. **Delete `data/jobs.db`** if it exists

### Files touched
- `src/video_to_essay/db.py` (rewrite)

---

## Phase 2: Auth (WorkOS AuthKit)

Add authentication to FastAPI. No frontend changes yet — just the backend routes and middleware.

### Steps

1. **Install WorkOS SDK**: `uv add workos`

2. **Add auth routes to `api.py`**:
   - `GET /api/auth/login` — generates WorkOS authorization URL, returns redirect
   - `GET /api/auth/callback` — exchanges code for sealed session, upserts `users` row, sets `wos_session` cookie, redirects to `/`
   - `GET /api/auth/logout` — clears cookie, redirects to login
   - `GET /api/auth/me` — returns current user info (for frontend to check auth state)

3. **Add auth dependency to FastAPI**:
   - Create a `get_current_user()` dependency that reads `wos_session` cookie, calls `session.authenticate()`, refreshes if needed, returns user dict or raises 401
   - Apply to all `/api/*` routes except health, auth, and static files

4. **Env vars needed**: `WORKOS_API_KEY`, `WORKOS_CLIENT_ID`, `WORKOS_COOKIE_PASSWORD`, `WORKOS_REDIRECT_URI`

### Files touched
- `src/video_to_essay/api.py` (add auth routes + dependency)
- `src/video_to_essay/db.py` (user queries already added in Phase 1)
- `pyproject.toml` (add workos dependency)
- `.env` (add WorkOS vars)

---

## Phase 3: API Endpoints

Replace the old job-based endpoints with the new video/channel/subscription endpoints.

### Steps

1. **Video endpoints**:
   - `POST /api/videos` — accepts `{url}`, extracts youtube_video_id, inserts into `videos` (if not exists) + `deliveries` (source=one_off), returns video id. Requires auth (user_id from session).
   - `GET /api/videos` — list videos for current user. Joins `deliveries` (for one-offs) and `videos` via `subscriptions` → `channels` → `videos.channel_id` (for subscriptions). Returns list with status derived from timestamps.
   - `GET /api/videos/{id}` — returns video metadata + status. If processed, fetches essay from S3 (`youtube/<video_id>/essay_final.md`). Includes delivery status for current user.

2. **Channel/subscription endpoints**:
   - `POST /api/channels` — accepts `{url}` (channel URL or video URL). Extracts youtube_channel_id (scrape page or use yt-dlp). Creates `channels` row if new + `subscriptions` row. Returns channel info.
   - `GET /api/channels` — list current user's subscriptions with channel info
   - `DELETE /api/subscriptions/{id}` — sets `active=false` (only if owned by current user)
   - `PATCH /api/subscriptions/{id}` — update `poll_interval_hours`

3. **Remove old endpoints**: delete `POST /api/jobs`, `GET /api/jobs/{job_id}`

### Files touched
- `src/video_to_essay/api.py` (rewrite endpoints)
- `src/video_to_essay/db.py` (add any missing query helpers)

---

## Phase 4: Workers

Refactor the existing single worker into four independent workers.

### Steps

1. **Discover worker** (`src/video_to_essay/discover_worker.py`):
   - Loop: query channels due for check (now - last_checked_at > min subscriber poll_interval_hours)
   - For each: fetch RSS feed via httpx, parse XML, extract video IDs
   - For new video IDs: insert into `videos` with `channel_id`
   - Update `channels.last_checked_at`

2. **Download worker** — skip for now (future, residential proxy). Add a stub or local fallback that uses existing `download_video()` and sets `downloaded_at`. This allows the pipeline to work end-to-end during development without S3.

3. **Process worker** (`src/video_to_essay/process_worker.py`):
   - Query: videos where `downloaded_at IS NOT NULL AND processed_at IS NULL AND error IS NULL`
   - Pull video from S3 (or local path during dev)
   - Run existing pipeline: transcribe → filter sponsors → essay → extract frames → place images
   - Upload artifacts to S3 (or write locally during dev)
   - Set `processed_at` on success, `error` on failure

4. **Deliver worker** (`src/video_to_essay/deliver_worker.py`):
   - One-offs: query `deliveries WHERE sent_at IS NULL` joined with processed videos
   - Subscriptions: find processed videos with channel_id, join subscriptions, check deliveries for already-sent
   - Send email via existing `send_essay()`
   - Insert/update delivery row with `sent_at`

5. **Update `main.py` serve command** to start all worker threads

6. **Refactor existing `worker.py`** — extract reusable pipeline logic, then delete old worker

### Files touched
- `src/video_to_essay/discover_worker.py` (new)
- `src/video_to_essay/process_worker.py` (new)
- `src/video_to_essay/deliver_worker.py` (new)
- `src/video_to_essay/worker.py` (delete after migration)
- `src/video_to_essay/main.py` (update serve command)

---

## Phase 5: Frontend — Layout & Auth

Rebuild the Next.js frontend with the sidebar layout and auth flow.

### Steps

1. **Sidebar layout component** (`web/app/components/Sidebar.tsx`):
   - App name, nav links (Videos, Subscriptions, Settings)
   - Subscribed channels list (fetched from `/api/channels`)
   - "+ Add channel" shortcut
   - Apply in `layout.tsx` as persistent sidebar

2. **Auth flow**:
   - `web/app/login/page.tsx` — button that redirects to `/api/auth/login`
   - Auth check wrapper: on app load, call `/api/auth/me`. If 401, redirect to login.
   - Logout: call `/api/auth/logout`

3. **Shared data fetching**:
   - Simple `fetch` wrapper that handles 401 → redirect to login
   - No global state library needed — fetch per page

### Files touched
- `web/app/layout.tsx` (add sidebar)
- `web/app/components/Sidebar.tsx` (new)
- `web/app/login/page.tsx` (new)
- `web/app/lib/api.ts` (new — fetch wrapper)

---

## Phase 6: Frontend — Dashboard

The main videos page.

### Steps

1. **URL input bar** at top — paste YouTube URL, submit to `POST /api/videos`
2. **Video list** — fetch from `GET /api/videos`, render rows with:
   - Video title, channel name or "One-off", relative date
   - Status: pulsing amber + step name (in progress), green "Ready →" (click → essay reader), red "Failed"
3. **Polling** — for any in-progress videos, poll `GET /api/videos` every 3 seconds. Stop when all are done/failed.

### Files touched
- `web/app/page.tsx` (rewrite)
- `web/app/status/page.tsx` (delete — status is now inline)

---

## Phase 7: Frontend — Essay Reader

### Steps

1. **Essay reader page** (`web/app/videos/[id]/page.tsx`):
   - Fetch `GET /api/videos/{id}` — includes essay HTML
   - Render: back link, metadata (channel, date, YouTube link), essay body
   - Essay rendered via `dangerouslySetInnerHTML` (HTML comes from our own pipeline, trusted)
   - Georgia serif styling for essay body, figure styling for images

### Files touched
- `web/app/videos/[id]/page.tsx` (new)

---

## Phase 8: Frontend — Subscriptions

### Steps

1. **Subscriptions page** (`web/app/subscriptions/page.tsx`):
   - "+ Add channel" input at top (paste channel or video URL) → `POST /api/channels`
   - List of subscribed channels from `GET /api/channels`
   - Per channel: name, poll interval dropdown (calls `PATCH /api/subscriptions/{id}`), unsubscribe button (calls `DELETE /api/subscriptions/{id}`)

### Files touched
- `web/app/subscriptions/page.tsx` (new)

---

## Phase 9: Frontend — Settings

### Steps

1. **Settings page** (`web/app/settings/page.tsx`):
   - Account info (email from `/api/auth/me`)
   - Default poll interval preference
   - Logout button

### Files touched
- `web/app/settings/page.tsx` (new)

---

## Phase 10: S3 Integration

Add S3/R2 as the artifact store. Until this phase, everything runs locally.

### Steps

1. **Add boto3**: `uv add boto3`
2. **Create `src/video_to_essay/storage.py`**:
   - `upload_file(local_path, s3_key)`
   - `download_file(s3_key, local_path)`
   - `get_file_content(s3_key)` — returns bytes (for essay reading)
   - `file_exists(s3_key)` — check if artifact exists
   - Configured via `S3_BUCKET`, `S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
3. **Update process worker** to upload artifacts after pipeline completes
4. **Update API** `GET /api/videos/{id}` to fetch essay from S3
5. **Update download worker stub** to upload video to S3 after download

### Files touched
- `src/video_to_essay/storage.py` (new)
- `src/video_to_essay/process_worker.py` (add S3 upload)
- `src/video_to_essay/api.py` (fetch essay from S3)
- `pyproject.toml` (add boto3)

---

## Dependency Order

```
Phase 1 (DB) → Phase 2 (Auth) → Phase 3 (API) → Phase 4 (Workers)
                                       ↓
                               Phase 5 (Frontend Layout & Auth)
                                       ↓
                            Phase 6 (Dashboard) → Phase 7 (Reader)
                                       ↓
                            Phase 8 (Subscriptions) → Phase 9 (Settings)

Phase 10 (S3) can happen in parallel after Phase 4
```

Phases 1-4 are backend. Phases 5-9 are frontend. Phase 10 is infrastructure.
Phases 6-9 are independent of each other once Phase 5 is done.
