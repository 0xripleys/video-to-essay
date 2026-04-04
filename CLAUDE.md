# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Converts YouTube videos into well-structured markdown essays with relevant images, delivered via email. Two interfaces: a CLI for manual single-video processing, and a web app + worker system for automated subscription-based delivery.

## Running

### Python CLI (pipeline)

```bash
uv sync                                    # Install deps (Python 3.14)
video-to-essay run <youtube_url>           # Full pipeline
video-to-essay run <youtube_url> --force   # Re-run all steps
video-to-essay essay <video_id>            # Run a single step
video-to-essay score <video_id>            # LLM-as-judge scoring
```

Common flags: `--cookies cookies.txt` (cloud IPs), `--force`, `--no-embed`, `--output-dir / -o`.

### Web app (Next.js)

```bash
cd web && npm install && npm run dev       # Dev server on :3000
```

### Workers (background processing)

Workers are started by importing `start_worker_threads()` from `video_to_essay.worker`. They require `DATABASE_URL`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID` in `.env`.

### No test suite

Verify changes manually by running against a real YouTube URL.

## Architecture

There are two systems that share a Supabase Postgres database:

1. **Web app** (`web/`) — Next.js frontend + API routes. Handles auth (WorkOS), video conversion requests, channel subscriptions. Dev mode bypasses auth when `WORKOS_API_KEY` is unset.
2. **Workers** (`src/video_to_essay/*_worker.py`) — Four Python daemon threads polling the database. See [`docs/architecture-workers-and-database.md`](docs/architecture-workers-and-database.md) for detailed schema, worker behavior, and data flow.

### Worker pipeline

```
discover (60s) → download (10s) → process (10s) → deliver (15s)
   │                  │                │                │
   │ RSS feed poll    │ yt-dlp         │ transcript →   │ create subscription
   │ → new video rows │ → video file   │ sponsors →     │ delivery rows
   │                  │ → metadata     │ essay →        │ → send via AgentMail
   │                  │                │ frames →       │
   │                  │                │ place images   │
```

### CLI pipeline (single video, `src/video_to_essay/`)

```
download → transcript (Deepgram) → filter sponsors → essay → extract frames → place images + annotate
```

Each step is idempotent (skips if output exists unless `--force`). Each step reads exactly one input file and fails if missing. Output goes to `runs/<video_id>/00_download/` through `05_place_images/`.

### Key modules (`src/video_to_essay/`)

- **`main.py`** — Typer CLI entry point, step orchestration
- **`db.py`** — Postgres schema, all DB queries (Python side)
- **`worker.py`** — Starts all 4 worker threads
- **`discover_worker.py`** — Polls YouTube RSS for new videos on subscribed channels
- **`download_worker.py`** — Downloads videos via yt-dlp
- **`process_worker.py`** — Runs full pipeline (transcript → essay → frames → images)
- **`deliver_worker.py`** — Creates subscription delivery rows, sends emails via AgentMail
- **`diarize.py`** — Deepgram transcription + speaker diarization
- **`transcriber.py`** — Essay generation (single/multi-speaker) + video download
- **`filter_sponsors.py`** — Haiku detects sponsor segments
- **`extract_frames.py`** — Frame sampling, pHash dedup, Haiku classification
- **`place_images.py`** — Sonnet places images + annotates figures (JSON-based approach)
- **`scorer.py`** — LLM-as-judge essay quality evaluation (5 dimensions, parallel API calls)
- **`email_sender.py`** — AgentMail integration, markdown → HTML email

### Web app (`web/`)

- **`app/lib/db.ts`** — Postgres queries (TypeScript side, same DB as Python workers)
- **`app/lib/auth.ts`** — WorkOS auth, `getCurrentUser()`, dev mode bypass
- **`app/api/`** — API routes for auth, videos, channels, subscriptions
- **`app/components/`** — React components (Dashboard, Landing, AppShell, modals)

## Key Technical Details

- **Database** — Supabase Postgres, shared between web app (TypeScript `pg`) and workers (Python `psycopg`). Both sides have their own query functions.
- **Auth** — WorkOS. Dev mode: if `WORKOS_API_KEY` is unset, auto-creates a `dev@localhost` user.
- **Claude models** — Sonnet (`claude-sonnet-4-5-20250929`) in `transcriber.py`, `place_images.py`, `scorer.py`. Haiku (`claude-haiku-4-5-20251001`) in `extract_frames.py`, `filter_sponsors.py`, `diarize.py`, `transcriber.py` (style profiles). Update all six files if changing models.
- **Deepgram** — `DEEPGRAM_API_KEY` required for transcription. Nova-3 with diarization.
- **YouTube** — yt-dlp with `--remote-components ejs:github` for JS challenges. Cloud IPs need `--cookies`. Requires `ffmpeg` and `deno` on PATH.
- **Email** — AgentMail API. Essays sent as HTML (inline-styled, sans-serif, 700px max-width) with plaintext fallback (80-char wrapped). Subject: `{Channel Name}: {Video Title}`.
- **Images in emails** — Worker pipeline (`process_worker.py`) uploads frames to S3 and rewrites image paths to pre-signed S3 URLs (7-day expiry) before saving `essay_final.md`. CLI pipeline (`main.py`) uses base64 data URIs via `embed_images()` instead.
- **No retries on failure** — Workers set `error` on the video/delivery row and move on. No automatic retry mechanism.

## Environment Variables

All stored in `.env` at project root:

| Variable | Used by | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | Workers + Web | Supabase Postgres connection string |
| `ANTHROPIC_API_KEY` | Workers (process) | Claude API for essay/frame/sponsor tasks |
| `DEEPGRAM_API_KEY` | Workers (process) | Deepgram Nova-3 transcription |
| `AGENTMAIL_API_KEY` | Workers (deliver) | Email sending |
| `AGENTMAIL_INBOX_ID` | Workers (deliver) | AgentMail sender inbox |
| `WORKOS_API_KEY` | Web | Auth (unset = dev mode) |
| `WORKOS_CLIENT_ID` | Web | Auth |
| `WORKOS_COOKIE_PASSWORD` | Web | Session cookie encryption |
| `S3_BUCKET_NAME` | Workers + Web | S3 bucket for run artifacts |
| `AWS_ACCESS_KEY_ID` | Workers + Web | AWS auth for S3 |
| `AWS_SECRET_ACCESS_KEY` | Workers + Web | AWS auth for S3 |
| `AWS_REGION` | Workers + Web | S3 bucket region (default: us-east-1) |

## Dependencies Beyond pip/npm

- `ffmpeg` — audio extraction and frame sampling
- `deno` — JS runtime for yt-dlp YouTube challenges
