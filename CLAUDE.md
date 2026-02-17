# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Converts YouTube videos into well-structured markdown essays with relevant images. Takes a YouTube URL, extracts the transcript, uses Claude API to generate an essay, downloads the video, extracts and classifies keyframes, and places them into the essay with figure annotations.

## Running the Tool

```bash
# Install deps (Python 3.14, prefer uv) — installs package in dev mode
uv sync

# Full end-to-end pipeline
ANTHROPIC_API_KEY=sk-... video-to-essay run <youtube_url>

# Individual steps (use video_id for steps after transcript)
video-to-essay transcript <url>              # Step 1: extract transcript
video-to-essay filter-sponsors <video_id>    # Step 2: detect/remove sponsor segments
video-to-essay essay <video_id>              # Step 3: generate essay
video-to-essay download <video_id>           # Step 4: download video
video-to-essay extract-frames <video_id>     # Step 5: extract + classify frames
video-to-essay place-images <video_id>       # Step 6-7: place images + annotate
video-to-essay score <video_id>              # Score essay quality vs transcript
video-to-essay score <video_id> -m claude-opus-4-20250514  # Score with Opus

# Alternative: run as module
python -m video_to_essay.main run <youtube_url>

# Common flags
--cookies cookies.txt    # Needed on cloud IPs (AWS/GCP/Azure block YouTube)
--force                  # Re-run steps even if outputs exist
--no-embed               # Disable base64 image embedding (embed is ON by default)
--output-dir / -o        # Base output directory (default: runs/)
```

No test suite yet. Verify changes manually by running against a real YouTube URL.

## Architecture

The package lives in `src/video_to_essay/`. `main.py` (typer CLI) orchestrates a 7-step pipeline (annotate is bundled into place-images). Each step is idempotent — it skips if output files already exist unless `--force` is passed.

### Pipeline flow

```
URL -> transcript -> filter sponsors -> essay -> download video -> extract frames -> place images + annotate
                          |                                              |
                   Haiku detects ad ranges                    sample (ffmpeg) -> dedup (pHash) -> classify (Haiku) -> filter
                   -> clean transcript                        sponsor ranges also used to drop frames
```

### Modules (all under `src/video_to_essay/`)

- **`main.py`** — CLI entry point, step orchestration. Output goes to `runs/<video_id>/`.
- **`transcriber.py`** — Transcript extraction + essay generation.
  - Tries `youtube-transcript-api` first, falls back to `yt-dlp`.
  - JSON3 parsing: yt-dlp's subtitle format has rolling duplicates marked with `aAppend`. `parse_json3()` filters these and groups into ~30s paragraphs with timestamps.
  - Essay generation uses "Simple Direct" prompt strategy (scored 8.5/10 on information coverage vs. 4 alternatives).
- **`filter_sponsors.py`** — Sponsor/ad detection and removal.
  - Uses Claude Haiku to identify sponsor reads/ad segments in the timestamped transcript.
  - Returns cleaned transcript (`transcript_clean.txt`) + timestamp ranges (`sponsor_segments.json`).
  - Sponsor ranges are also passed downstream to `extract_frames` to skip frames during ad segments.
- **`extract_frames.py`** — Frame sampling, dedup, classification, filtering.
  - Sample 1 frame every 5s via ffmpeg
  - Perceptual hash (pHash) dedup with Hamming distance ≤ 8
  - Classify unique frames with Claude Haiku + nearby transcript context
  - Keep frames with value ≥ 3, skip "talking_head", "transition", and "advertisement" categories
- **`place_images.py`** — Image placement + figure annotation.
  - `place`: Claude inserts `![](images/frame_*.jpg)` at contextual positions
  - `annotate`: mechanical figure numbering, then Claude in batches weaves "(see Figure N)" into prose
- **`scorer.py`** — LLM-as-judge essay quality evaluation.
  - Scores essay vs transcript on 5 dimensions: faithfulness, proportionality, embellishment, hallucination, tone.
  - Each dimension is scored in a separate parallel API call (tool use for structured output). Summary is built from rationales in Python.
  - Includes exponential backoff retry on rate limits (5 parallel calls can exceed 30k input tokens/min).
  - Defaults to Sonnet; use `--model` to switch (e.g. Opus for stricter judging, Haiku for quick checks).
  - TODO: chunk scoring for long videos (3+ hours) — 20-min windows with 5-min overlap, proportionality stays global.

### Output structure

```
runs/<video_id>/
  metadata.json, transcript.txt, transcript_clean.txt, sponsor_segments.json
  essay.md, video.mp4
  frames/ { raw/, kept/, classifications.json }
  essay_with_images.md, essay_final.md
```

## Key Technical Details

- **YouTube blocks cloud IPs** — Pass `--cookies` with a Netscape-format cookies.txt. Cookies rotate quickly when used from different IPs.
- **yt-dlp requires `--remote-components ejs:github`** for YouTube JS challenges, plus `deno` on PATH.
- **Claude models** — Sonnet (`claude-sonnet-4-5-20250929`) is hardcoded in `transcriber.py`, `place_images.py`, and `scorer.py` for essay/image/scoring tasks. Haiku (`claude-haiku-4-5-20251001`) is used in `extract_frames.py` and `filter_sponsors.py`. Update all five files if changing models.
- **Essay step prefers cleaned transcript** — `_step_essay` in `main.py` reads `transcript_clean.txt` if it exists, falling back to `transcript.txt`.
- **Known output issues** (see ISSUES.md): speaker attribution lost, over-formalized tone, AI embellishment beyond source material.

## Dependencies Beyond pip

- `ffmpeg` — needed by yt-dlp and frame extraction
- `deno` — JS runtime for yt-dlp YouTube challenges
