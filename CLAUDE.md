# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Converts YouTube videos into well-structured markdown essays with relevant images. Takes a YouTube URL, extracts the transcript, uses Claude API to generate an essay, downloads the video, extracts and classifies keyframes, and places them into the essay with figure annotations.

## Running the Tool

```bash
# Install deps (Python 3.14, prefer uv) — installs package in dev mode
uv sync

# Full end-to-end pipeline (requires both API keys)
DEEPGRAM_API_KEY=... ANTHROPIC_API_KEY=sk-... video-to-essay run <youtube_url>

# Individual steps (use video_id for steps after download)
video-to-essay download <video_id>           # Step 0: download video + metadata
video-to-essay transcript <url>              # Step 0+1: download + Deepgram transcript
video-to-essay diarize <video_id>            # Standalone: download + diarize
video-to-essay filter-sponsors <video_id>    # Step 2: detect/remove sponsor segments
video-to-essay essay <video_id>              # Step 3: generate essay
video-to-essay extract-frames <video_id>     # Step 4: extract + classify frames
video-to-essay place-images <video_id>       # Step 5-6: place images + annotate
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

The package lives in `src/video_to_essay/`. `main.py` (typer CLI) orchestrates a 6-step pipeline (annotate is bundled into place-images). Each step is idempotent — it skips if output files already exist unless `--force` is passed. Each step reads exactly one expected input file and fails if it's missing.

### Pipeline flow

```
URL -> download video -> transcript (Deepgram) -> filter sponsors -> essay -> extract frames -> place images + annotate
            |                    |                      |                           |
     yt-dlp video+meta    extract audio (ffmpeg)  Haiku detects ad ranges    sample (ffmpeg) -> dedup (pHash) -> classify (Haiku) -> filter
                          -> Deepgram API          -> clean transcript        sponsor ranges also used to drop frames
                          -> speaker mapping
```

Transcript step (requires `DEEPGRAM_API_KEY`):
```
extract audio (ffmpeg -vn) -> Deepgram API (nova-3, diarize) -> speaker name mapping (Haiku, multi-speaker only) -> format transcript
```

### Modules (all under `src/video_to_essay/`)

- **`main.py`** — CLI entry point, step orchestration. Output goes to `runs/<video_id>/`.
- **`diarize.py`** — Deepgram transcription + speaker diarization.
  - `extract_audio()` — ffmpeg audio extraction from video to `audio.mp3`.
  - `run_diarization()` — POST to Deepgram Nova-3 API with `diarize=true&utterances=true&smart_format=true`. Uses `httpx`.
  - `map_speaker_names()` — Only called when >1 speaker. Sends first ~80 utterances + video metadata to Haiku to map speaker IDs to real names.
  - `format_transcript()` — Groups consecutive utterances by same speaker. Multi-speaker: `**Speaker Name** [MM:SS]` format. Single-speaker: `[MM:SS] Text` format.
  - `transcribe_with_deepgram()` — Top-level orchestrator. Raises `RuntimeError` if `DEEPGRAM_API_KEY` missing. Always writes to `transcript.txt`.
- **`transcriber.py`** — Essay generation and video download.
  - `fetch_video_metadata()` — yt-dlp `--dump-json` wrapper for title/description/channel.
  - `download_video()` — yt-dlp video download.
  - Essay generation detects single vs multi-speaker transcripts:
    - **Single-speaker**: `extract_style_profile()` → system prompt with KEEP/NEVER rules → monologue essay.
    - **Multi-speaker**: `extract_multi_speaker_style_profile()` → per-speaker profiles → dialogue-style essay preserving conversational back-and-forth with `**Speaker Name**: text` format.
  - Style-preserving prompt uses 3 techniques: style profiling, KEEP/NEVER constraints, contrastive few-shot examples.
- **`filter_sponsors.py`** — Sponsor/ad detection and removal.
  - Uses Claude Haiku to identify sponsor reads/ad segments in the timestamped transcript.
  - Returns cleaned transcript (`transcript_clean.txt`) + timestamp ranges (`sponsor_segments.json`).
  - Sponsor ranges are also passed downstream to `extract_frames` to skip frames during ad segments.
- **`extract_frames.py`** — Frame sampling, dedup, classification, filtering.
  - Sample 1 frame every 5s via ffmpeg
  - Perceptual hash (pHash) dedup with Hamming distance ≤ 8
  - Classify unique frames with Claude Haiku + nearby transcript context
  - Keep frames with value ≥ 3, skip "talking_head", "transition", and "advertisement" categories
- **`place_images.py`** — Image placement + figure annotation. Both stages use a JSON-based approach to avoid output token limits on long essays.
  - `place`: paragraphs numbered `[P0]`, `[P1]`…, Sonnet returns JSON `[{image, after, alt}]`, images inserted mechanically.
  - `annotate`: mechanical figure numbering (`*Figure N: alt*`), then Sonnet in batches of 5 returns JSON `[{figure, find, replace}]` to weave "(see Figure N)" into prose via string replacement.
  - Both stages include `_stream_message()` with exponential backoff retry on rate limits.
- **`scorer.py`** — LLM-as-judge essay quality evaluation.
  - Scores essay vs transcript on 5 dimensions: faithfulness, proportionality, embellishment, hallucination, tone.
  - Each dimension is scored in a separate parallel API call (tool use for structured output). Summary is built from rationales in Python.
  - Includes exponential backoff retry on rate limits (5 parallel calls can exceed 30k input tokens/min).
  - Defaults to Sonnet; use `--model` to switch (e.g. Opus for stricter judging, Haiku for quick checks).
  - TODO: chunk scoring for long videos (3+ hours) — 20-min windows with 5-min overlap, proportionality stays global.

### Output structure

```
runs/<video_id>/
  metadata.json                     # URL, video_id, title, description, channel, etc.
  video.mp4                         # Downloaded video (may be .webm)
  audio.mp3                         # Extracted from video via ffmpeg
  diarization.json                  # Deepgram utterances with speaker IDs
  deepgram_response.json            # Full Deepgram API response
  speaker_map.json                  # Speaker ID → name (multi-speaker only)
  transcript.txt                    # Deepgram transcript (with **Speaker** markers if multi-speaker)
  transcript_clean.txt, sponsor_segments.json
  essay.md
  frames/ { raw/, kept/, classifications.json }
  essay_with_images.md, essay_final.md
```

## Key Technical Details

- **YouTube blocks cloud IPs** — Pass `--cookies` with a Netscape-format cookies.txt. Cookies rotate quickly when used from different IPs.
- **yt-dlp requires `--remote-components ejs:github`** for YouTube JS challenges, plus `deno` on PATH.
- **Claude models** — Sonnet (`claude-sonnet-4-5-20250929`) is hardcoded in `transcriber.py`, `place_images.py`, and `scorer.py` for essay/image/scoring tasks. Haiku (`claude-haiku-4-5-20251001`) is used in `extract_frames.py`, `filter_sponsors.py`, `diarize.py:map_speaker_names()`, and `transcriber.py:extract_style_profile()/extract_multi_speaker_style_profile()`. Update all six files if changing models.
- **Deepgram API key** — Set `DEEPGRAM_API_KEY` in `.env` or environment. **Required** — the pipeline fails with a clear error if missing. Get a free key at https://console.deepgram.com/signup
- **No fallbacks** — Each step reads exactly one file and fails if missing. The transcript step writes `transcript.txt` (with `**Speaker**` markers if multi-speaker). The essay step reads only `transcript_clean.txt`. The extract-frames step requires both `transcript.txt` and `sponsor_segments.json`.
- **Speaker attribution** — Deepgram diarization solves the speaker attribution problem for multi-speaker content. Single-speaker videos get better transcription quality from Deepgram Nova-3 vs YouTube auto-captions.

## Dependencies Beyond pip

- `ffmpeg` — needed by yt-dlp and frame extraction
- `deno` — JS runtime for yt-dlp YouTube challenges
