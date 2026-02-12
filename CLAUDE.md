# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Converts YouTube videos into well-structured markdown essays with relevant images. Takes a YouTube URL, extracts the transcript, and uses Claude API to generate a polished essay.

## Running the Tool

```bash
pip install -r requirements.txt

# Transcript only
python transcriber.py <youtube_url> --transcript-only

# Full essay
ANTHROPIC_API_KEY=sk-... python transcriber.py <youtube_url> -o essay.md

# With YouTube cookies (needed on cloud IPs)
python transcriber.py <youtube_url> --cookies cookies.txt -o essay.md
```

No test suite yet. Verify changes manually by running against a real YouTube URL.

## Architecture

Single-file tool (`transcriber.py`) with this pipeline:

1. **Transcript extraction** — tries `youtube-transcript-api` first (lightweight, no video download), falls back to `yt-dlp` (needs cookies on cloud IPs, needs `deno` JS runtime)
2. **JSON3 parsing** — yt-dlp's JSON3 subtitle format has rolling duplicate lines marked with `aAppend`. The `parse_json3()` function filters these out and groups text into ~30s paragraphs with timestamps.
3. **Essay generation** — sends transcript to Claude Sonnet 4.5 with a minimal "Simple Direct" prompt. This strategy scored 8.5/10 on information coverage, beating 4 other tested approaches.

## Key Technical Details

- **YouTube blocks cloud IPs** — both `youtube-transcript-api` and `yt-dlp` get blocked from AWS/GCP/Azure. Pass `--cookies` with a fresh Netscape-format cookies.txt exported from a browser. Cookies get rotated quickly when used from a different IP.
- **yt-dlp requires `--remote-components ejs:github`** flag for YouTube JS challenge solving, plus `deno` installed and on PATH.
- **Image extraction is not yet implemented** — PySceneDetect and ffmpeg are listed as dependencies for future frame extraction from downloaded videos. See PLAN.md Phase 2.

## Dependencies Beyond pip

- `ffmpeg` — static binary, needed by yt-dlp and scenedetect
- `deno` — JS runtime, needed by yt-dlp for YouTube's JS challenges
