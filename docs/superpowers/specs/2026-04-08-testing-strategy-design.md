# Testing Strategy — Comprehensive Test Wishlist

**Date:** 2026-04-08
**Status:** In Progress — pure tests complete (43/43), remaining: db, db+mock, db+s3, smoke

## Overview

A comprehensive inventory of tests for the video-to-essay project, organized by component. Each test is tagged with its infrastructure requirements:

- **[pure]** — No external dependencies. Fast, zero infrastructure.
- **[db]** — Needs a Postgres instance (Testcontainers).
- **[db+mock]** — Needs Postgres + mocked external APIs (YouTube, S3, etc.).
- **[db+s3]** — Needs Postgres + S3 (LocalStack via Testcontainers).
- **[smoke]** — Build/lint checks only.

## Infrastructure Plan

- **Python test runner:** pytest
- **Database:** `testcontainers-postgres` — spins up throwaway Postgres per test session
- **S3 (if needed):** LocalStack via Testcontainers
- **Web smoke test:** `npm run build`
- **CI:** GitHub Actions on push/PR
- **Local:** `uv run pytest` and `npm test`
- **Pre-commit hook:** runs pytest + ruff check

---

## Python — CLI Pipeline

### `transcriber.py`

| # | Test | Tag |
|---|------|-----|
| 1 | `extract_video_id` — standard URLs (`youtube.com/watch?v=`, `youtu.be/`, bare 11-char ID) | [pure] |
| 2 | `extract_video_id` — rejects invalid URLs (too short, wrong domain) | [pure] |
| 3 | `_is_multi_speaker` — returns True for `**Speaker** [MM:SS]` format | [pure] |
| 4 | `_is_multi_speaker` — returns False for `[MM:SS] text` format | [pure] |
| 5 | `_extract_speakers` — extracts unique names, preserves insertion order | [pure] |
| 6 | `_timestamp_instructions` — generates correct YouTube link format with total seconds | [pure] |

### `filter_sponsors.py`

| # | Test | Tag |
|---|------|-----|
| 7 | `_parse_mmss` — "05:30" -> 330, "0:00" -> 0, invalid -> None | [pure] |
| 8 | `_strip_segments` — removes paragraphs within time ranges, keeps others | [pure] |
| 9 | `_strip_segments` — handles multi-speaker format (`**Speaker** [MM:SS]`) | [pure] |
| 10 | `_strip_segments` — empty ranges returns transcript unchanged | [pure] |
| 11 | `_strip_segments` — paragraphs without timestamps are always kept | [pure] |

### `extract_frames.py`

| # | Test | Tag |
|---|------|-----|
| 12 | `parse_transcript` — single-speaker `[MM:SS] text` format | [pure] |
| 13 | `parse_transcript` — multi-speaker `**Name** [MM:SS]\ntext` format | [pure] |
| 14 | `parse_transcript` — empty/malformed input returns empty list | [pure] |
| 15 | `get_transcript_context` — returns text within +/- window seconds | [pure] |
| 16 | `get_transcript_context` — returns empty string when no entries in window | [pure] |
| 17 | `frame_seconds` — `frame_0001.jpg` with interval=5 -> 0, `frame_0003.jpg` -> 10 | [pure] |
| 18 | `frame_timestamp` — correct MM:SS formatting from frame filename | [pure] |
| 19 | `_in_sponsor_range` — inside range -> True, outside -> False, padding works | [pure] |
| 20 | `encode_image_base64` — roundtrips correctly (encode then decode matches bytes) | [pure] |
| 21 | `dedup_frames` — identical frames collapse to one, different frames kept (needs test images, no API) | [pure] |

### `place_images.py`

| # | Test | Tag |
|---|------|-----|
| 22 | `format_frame_list` — formats frames into expected `- images/frame.jpg [MM:SS] - desc` lines | [pure] |
| 23 | `load_kept_frames` — filters classifications to only frames present in kept dir | [pure] |
| 24 | `_number_figures` — `![alt](src)` becomes numbered figure with caption | [pure] |
| 25 | `_number_figures` — counter increments correctly across multiple images | [pure] |
| 26 | `_resize_for_email` — output is smaller than input, produces valid JPEG | [pure] |
| 27 | `embed_images` — replaces `images/frame_0001.jpg` with `data:image/jpeg;base64,...` | [pure] |
| 28 | `embed_images` — missing frame file leaves original path unchanged | [pure] |

### `diarize.py`

| # | Test | Tag |
|---|------|-----|
| 29 | `format_transcript` — single-speaker: groups consecutive segments, `[MM:SS] text` | [pure] |
| 30 | `format_transcript` — multi-speaker: `**Name** [MM:SS]\ntext` with speaker names | [pure] |
| 31 | `format_transcript` — empty segments returns empty string | [pure] |
| 32 | `format_transcript` — consecutive same-speaker segments get merged | [pure] |

### `email_sender.py`

| # | Test | Tag |
|---|------|-----|
| 33 | `_essay_to_html` — produces valid HTML with inline styles, 700px max-width div | [pure] |
| 34 | `_insert_scrivi_link` — inserts after Key Takeaways section, before `---` | [pure] |
| 35 | `_insert_scrivi_link` — fallback: inserts after H1 when no Key Takeaways present | [pure] |
| 36 | Plaintext generation — base64 images replaced with `[Image: alt]` | [pure] |
| 37 | Plaintext wrapping — lines wrapped at 80 chars, headings and blockquotes preserved | [pure] |

### `summarize.py`

| # | Test | Tag |
|---|------|-----|
| 38 | `_strip_takeaways` — removes existing Key Takeaways section cleanly | [pure] |

### `discover_worker.py`

| # | Test | Tag |
|---|------|-----|
| 39 | `_uploads_playlist_id` — `UCxxx` -> `UUxxx` conversion | [pure] |
| 40 | `_parse_iso8601_duration` — `PT1H2M30S` -> 3750, `PT45S` -> 45, `PT0S` -> 0, empty -> 0 | [pure] |

### `scorer.py`

| # | Test | Tag |
|---|------|-----|
| 41 | `score_essay` return shape — correct keys (overall_score, dimensions, summary, model) | [pure] |

### `s3.py`

| # | Test | Tag |
|---|------|-----|
| 42 | `get_public_url` — correct URL format `https://{bucket}.s3.{region}.amazonaws.com/{key}` | [pure] |
| 43 | `_content_type` — `.jpg` -> `image/jpeg`, `.json` -> `application/json`, unknown -> `application/octet-stream` | [pure] |

---

## Python — Database (`db.py`)

### Basic CRUD

| # | Test | Tag |
|---|------|-----|
| 44 | `init_db` — creates all tables and runs migrations without error | [db] |
| 45 | `create_user` + `get_user_by_workos_id` — roundtrip | [db] |
| 46 | `upsert_user` — creates on first call, returns existing on second | [db] |
| 47 | `create_channel` + `get_channel_by_youtube_id` — roundtrip | [db] |
| 48 | `get_or_create_channel` — idempotent (same result on repeated calls) | [db] |
| 49 | `create_video` + `get_video` — roundtrip with all fields including arrays | [db] |
| 50 | `get_or_create_video` — idempotent | [db] |
| 51 | `create_subscription` + `get_subscription` — roundtrip | [db] |

### State Transitions

| # | Test | Tag |
|---|------|-----|
| 52 | `mark_video_downloaded` — sets `downloaded_at`, optionally updates title | [db] |
| 53 | `mark_video_processed` — sets `processed_at` | [db] |
| 54 | `mark_video_failed` — sets `error` field | [db] |
| 55 | `deactivate_subscription` — sets `active = FALSE` | [db] |

### Queue Queries

| # | Test | Tag |
|---|------|-----|
| 56 | `get_videos_pending_download` — returns videos with no `downloaded_at` and no `error` | [db] |
| 57 | `get_videos_pending_processing` — returns downloaded but unprocessed videos | [db] |
| 58 | `get_channels_due_for_check` — respects poll interval, returns channels past due | [db] |
| 59 | `get_channels_due_for_check` — ignores channels with no active subscriptions | [db] |

### Delivery Logic

| # | Test | Tag |
|---|------|-----|
| 60 | `create_delivery` — returns ID on first call, None on duplicate (unique constraint) | [db] |
| 61 | `create_subscription_deliveries` — creates rows for processed videos with active subscriptions | [db] |
| 62 | `create_subscription_deliveries` — respects `playlist_ids` filter (array overlap `&&`) | [db] |
| 63 | `create_subscription_deliveries` — respects `exclude_livestreams` flag | [db] |
| 64 | `create_subscription_deliveries` — skips already-delivered video/user combos | [db] |
| 65 | `get_pending_deliveries` — returns only unsent deliveries for processed videos | [db] |
| 66 | `mark_delivery_sent` / `mark_delivery_failed` — updates correct fields | [db] |

### Listing Queries

| # | Test | Tag |
|---|------|-----|
| 67 | `list_user_subscriptions` — returns only active subs with joined channel info | [db] |
| 68 | `list_user_videos` — returns one-off + subscription videos, deduped by video ID | [db] |
| 69 | `get_channel_subscriptions` — returns only active subs for a channel | [db] |

---

## Python — Worker Integration

| # | Test | Tag |
|---|------|-----|
| 70 | Discover `_check_channel` — inserts new videos, skips existing, skips shorts, respects cutoff date | [db+mock] |
| 71 | Discover — respects playlist filtering via `_check_playlist_membership` | [db+mock] |
| 72 | Discover — skips active livestreams, respects `exclude_livestreams` subscriber pref | [db+mock] |
| 73 | Download `_download_one` — marks video downloaded after success, marks failed on error | [db+mock] |
| 74 | Deliver `_deliver` — marks sent on success, marks failed when essay not found | [db+mock] |
| 75 | Deliver — retries on 429 rate limits, fails after max retries | [db+mock] |

---

## Web App — API Routes

### Auth

| # | Test | Tag |
|---|------|-----|
| 76 | `GET /api/auth/me` — returns 401 when no session | [smoke] |
| 77 | `GET /api/auth/me` — returns user in dev mode (no `WORKOS_API_KEY`) | [smoke] |

### Videos

| # | Test | Tag |
|---|------|-----|
| 78 | `POST /api/videos` — creates video + delivery from valid YouTube URL | [db] |
| 79 | `POST /api/videos` — rejects invalid YouTube URLs | [db] |
| 80 | `GET /api/videos` — returns videos with correct status enum (pending_download, processing, done, failed) | [db] |
| 81 | `GET /api/videos/[videoId]` — returns essay markdown from S3 when status is done | [db+s3] |

### Channels

| # | Test | Tag |
|---|------|-----|
| 82 | `POST /api/channels` — creates channel + subscription from YouTube channel URL | [db] |
| 83 | `GET /api/channels` — lists subscriptions with video counts | [db] |
| 84 | `POST /api/channels` — rejects duplicate subscription for same user+channel | [db] |

### Subscriptions

| # | Test | Tag |
|---|------|-----|
| 85 | `DELETE /api/subscriptions/[subId]` — deactivates subscription | [db] |
| 86 | `PATCH /api/subscriptions/[subId]` — updates poll_interval_hours and playlist_ids | [db] |
| 87 | `PATCH /api/subscriptions/[subId]` — rejects invalid poll_interval values | [db] |

### Proxy

| # | Test | Tag |
|---|------|-----|
| 88 | `GET /api/proxy/image` — rejects non-YouTube hosts | [pure] |
| 89 | `GET /api/proxy/image` — rejects missing URL parameter | [pure] |

### Health

| # | Test | Tag |
|---|------|-----|
| 90 | `GET /api/health` — returns `{ status: "ok" }` | [smoke] |

---

## Build / Lint Smoke Tests

| # | Test | Tag |
|---|------|-----|
| 91 | `npm run build` — Next.js builds without errors (catches type errors, broken imports) | [smoke] |
| 92 | `uv run python -c "import video_to_essay"` — Python package imports cleanly | [smoke] |
| 93 | `ruff check` — no lint errors | [smoke] |

---

## Summary by Infrastructure

| Tag | Count | What it catches | Infrastructure | Status |
|-----|-------|-----------------|---------------|--------|
| [pure] | 43 | Parsing bugs, formatting regressions, data transformation errors | Nothing | **Done** (86 pytest cases) |
| [db] | 26 | SQL bugs, schema drift, query logic errors | Testcontainers Postgres | Not started |
| [db+mock] | 6 | Worker pipeline logic, state machine errors | Postgres + mocked YouTube/S3/email APIs | Not started |
| [db+s3] | 1 | S3 integration in API routes | Postgres + LocalStack | Not started |
| [smoke] | 5 | Build failures, import errors, lint regressions | Build tools only | Not started |
| **Total** | **81** | | | |

## Recommended Implementation Order

1. ~~**[pure] tests (43)** — Zero infrastructure, runs in <1s. Highest ROI.~~ **Done** (2026-04-08)
2. **[smoke] tests (5)** — One-liners that catch build/import/lint regressions.
3. **[db] tests (26)** — Add Testcontainers fixture, test all SQL queries.
4. **[db+mock] worker tests (6)** — Add after the above are stable.
5. **[db+s3] tests (1)** — Only if S3 integration becomes a pain point.

## CI Pipeline

```yaml
# GitHub Actions: on push and PR
jobs:
  test-python:
    - uv sync
    - ruff check
    - uv run pytest tests/ -x

  test-web:
    - cd web && npm ci
    - npm run build
```

## Pre-commit Hook

```bash
# .pre-commit: runs before each commit
ruff check --fix
uv run pytest tests/ -x --timeout=30
```
