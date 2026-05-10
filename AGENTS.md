# AGENTS.md

This file provides guidance to Codex and other AI coding agents when working with code in this repository.

## What This Project Does

Converts YouTube videos into well-structured markdown essays with relevant images, delivered via email. It has two interfaces: a CLI for manual single-video processing, and a web app plus worker system for automated subscription-based delivery.

## Running

### Python CLI Pipeline

```bash
uv sync
video-to-essay run <youtube_url>
video-to-essay run <youtube_url> --force
video-to-essay essay <video_id>
video-to-essay score <video_id>
```

Common flags: `--cookies cookies.txt` for cloud IPs, `--force`, `--no-embed`, and `--output-dir` / `-o`.

```bash
video-to-essay serve
video-to-essay worker discover
```

`serve` starts all four workers in-process. A single worker can be run with `worker discover`, `worker download`, `worker process`, or `worker deliver`.

### Web App

```bash
cd web && npm install && npm run dev
```

The Next.js dev server runs on port `3000`.

### Background Workers

Workers are started by importing `start_worker_threads()` from `video_to_essay.worker`. They require these environment variables in `.env`: `DATABASE_URL`, `OPENROUTER_API_KEY`, `DEEPGRAM_API_KEY`, `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`, and `YOUTUBE_API_KEY`.

On macOS, each worker runs as a LaunchAgent at `~/Library/LaunchAgents/com.video-to-essay.*.plist`. Restart them with:

```bash
launchctl unload ~/Library/LaunchAgents/com.video-to-essay.*.plist
launchctl load ~/Library/LaunchAgents/com.video-to-essay.*.plist
```

Worker logs are written to `logs/`: `discover.log`, `download.log`, `process.log`, and `deliver.log`.

### Tests

```bash
uv run pytest tests/ -x --ignore=tests/test_smoke.py --ignore=tests/db/
uv run pytest tests/db/ -x
uv run pytest tests/test_smoke.py -x -k "not nextjs"
uv run pytest tests/ -x -v
uv run ruff check
```

Use the pure Python tests for fast validation. DB tests require Docker and use Testcontainers to spin up a throwaway Postgres 16 container per session. On macOS, `tests/db/conftest.py` auto-detects Docker Desktop's non-standard socket at `~/.docker/run/docker.sock`; DB tests will fail if Docker is not running.

CI runs via GitHub Actions in `.github/workflows/ci.yml`: `test-python`, `test-database`, `test-web`, and a coverage merge job. For integration testing, verify changes manually against a real YouTube URL.

## Architecture

Two systems share a Supabase Postgres database:

1. `web/` is the Next.js frontend plus API routes. It handles WorkOS auth, video conversion requests, channel subscriptions, and dev-mode auth bypass when `WORKOS_API_KEY` is unset.
2. `src/video_to_essay/*_worker.py` contains four Python daemon workers that poll the database. See `docs/architecture-workers-and-database.md` for detailed schema, worker behavior, and data flow.

### Worker Pipeline

```text
discover (60s) -> download (10s) -> process (10s) -> deliver (15s)
   |                  |                |                |
   | YouTube API poll | yt-dlp         | transcript ->  | create subscription
   | -> new rows      | -> video file  | sponsors ->    | delivery rows
   |                  | -> metadata    | essay ->       | -> send via AgentMail
   |                  |                | frames ->      |
   |                  |                | place images   |
```

### CLI Pipeline

```text
download -> transcript (Deepgram) -> filter sponsors -> essay -> extract frames -> place images + annotate
```

Each step is idempotent and skips existing output unless `--force` is passed. Each step reads exactly one input file and fails if that input is missing. Output goes to `runs/<video_id>/00_download/` through `05_place_images/`.

## Key Modules

### Python

- `src/video_to_essay/main.py` is the Typer CLI entry point and step orchestrator.
- `src/video_to_essay/db.py` owns the Postgres schema and Python-side DB queries.
- `src/video_to_essay/worker.py` starts all four worker threads.
- `src/video_to_essay/discover_worker.py` polls the YouTube Data API for new videos on subscribed channels.
- `src/video_to_essay/download_worker.py` downloads videos with `yt-dlp`.
- `src/video_to_essay/process_worker.py` runs the full pipeline.
- `src/video_to_essay/deliver_worker.py` creates subscription delivery rows and sends emails through AgentMail.
- `src/video_to_essay/diarize.py` handles Deepgram transcription and speaker diarization.
- `src/video_to_essay/transcriber.py` handles essay generation and video download.
- `src/video_to_essay/filter_sponsors.py` uses DeepSeek to detect sponsor segments.
- `src/video_to_essay/extract_frames.py` handles frame sampling, pHash deduplication, and Gemini Flash Lite classification.
- `src/video_to_essay/place_images.py` uses DeepSeek to place images and annotate figures.
- `src/video_to_essay/scorer.py` performs LLM-as-judge essay quality evaluation.
- `src/video_to_essay/email_sender.py` converts markdown to HTML email and sends through AgentMail.
- `src/video_to_essay/s3.py` uploads run artifacts to S3.
- `src/video_to_essay/analytics.py` tracks server-side PostHog events.

### Web

- `web/app/lib/db.ts` contains TypeScript-side Postgres queries against the same DB as the Python workers.
- `web/app/lib/auth.ts` handles WorkOS auth and `getCurrentUser()`.
- `web/app/api/` contains API routes for auth, videos, channels, and subscriptions.
- `web/app/components/` contains React components such as Dashboard, Landing, AppShell, and modals.

## Key Technical Details

- Database: Supabase Postgres shared by the web app (`pg`) and workers (`psycopg`). Both sides maintain their own query functions.
- Auth: WorkOS. If `WORKOS_API_KEY` is unset, dev mode auto-creates a `dev@localhost` user.
- LLM calls: all routed through `src/video_to_essay/llm.py`, a thin LiteLLM wrapper. Persistent model defaults live in the `MODELS` dict at the top of that file. Current production defaults use DeepSeek V3.1 via OpenRouter for text tasks and image placement, Gemini Flash Lite via OpenRouter for frame classification, and Sonnet for explicit scoring/evaluation. For ad-hoc experiments, pass `--model <litellm-string>` to supported single-step CLI subcommands.
- LLM call logs: each call is persisted as JSON to `<step_dir>/llm_calls/`. Base64 image bytes are stripped to sha256 and size references to avoid duplicating frames already on S3.
- Deepgram: `DEEPGRAM_API_KEY` is required for transcription. The project uses Nova-3 with diarization.
- YouTube: `yt-dlp` uses `--remote-components ejs:github` for JS challenges. Cloud IPs need `--cookies`. `ffmpeg` and `deno` must be on `PATH`.
- Email: AgentMail sends HTML essays with plaintext fallback. Subject format is `{Channel Name}: {Video Title}`.
- Images in emails: the worker pipeline uploads frames to S3 and rewrites image paths to public S3 URLs before saving `essay_final.md`. The CLI pipeline uses base64 data URIs through `embed_images()`.
- Worker failures: workers set `error` on the video or delivery row and move on. There is no automatic retry mechanism.

## Environment Variables

All are stored in `.env` at the project root.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Workers + Web | Supabase Postgres connection string |
| `OPENROUTER_API_KEY` | Workers + CLI | OpenRouter API for default text and vision LLM tasks |
| `ANTHROPIC_API_KEY` | CLI | Claude API for scorer/evaluation tasks |
| `DEEPGRAM_API_KEY` | Workers | Deepgram Nova-3 transcription |
| `AGENTMAIL_API_KEY` | Workers | Email sending |
| `AGENTMAIL_INBOX_ID` | Workers | AgentMail sender inbox |
| `YOUTUBE_API_KEY` | Workers | YouTube Data API for polling new uploads |
| `WORKOS_API_KEY` | Web | Auth; unset enables dev mode |
| `WORKOS_CLIENT_ID` | Web | Auth |
| `WORKOS_COOKIE_PASSWORD` | Web | Session cookie encryption |
| `S3_BUCKET_NAME` | Workers + Web | S3 bucket for run artifacts |
| `AWS_ACCESS_KEY_ID` | Workers + Web | AWS auth for S3 |
| `AWS_SECRET_ACCESS_KEY` | Workers + Web | AWS auth for S3 |
| `AWS_REGION` | Workers + Web | S3 bucket region, default `us-east-1` |
| `SENTRY_DSN` | Workers + CLI | Sentry DSN for Python error monitoring |
| `NEXT_PUBLIC_SENTRY_DSN` | Web | Sentry DSN for Next.js error monitoring |
| `NEXT_PUBLIC_POSTHOG_KEY` | Web | PostHog project API key |
| `NEXT_PUBLIC_POSTHOG_HOST` | Web | PostHog ingest host, default `us.i.posthog.com` |
| `POSTHOG_API_KEY` | Workers | PostHog project API key for server-side events |

## Dependencies Beyond pip/npm

- `ffmpeg` for audio extraction and frame sampling.
- `deno` for `yt-dlp` YouTube JavaScript challenges.

## Agent Notes

- Prefer `rg` and `rg --files` for search.
- Do not commit generated run artifacts, logs, coverage files, local env files, or package installers.
- Treat `.env` and `.env.local` as local secrets. Do not print their contents in responses.
- Before changing database behavior, inspect both `src/video_to_essay/db.py` and `web/app/lib/db.ts` because schema/query expectations are duplicated across Python and TypeScript.
- For worker behavior changes, consider the full `discover -> download -> process -> deliver` lifecycle and verify whether errors should be row-level, delivery-level, or fatal.
