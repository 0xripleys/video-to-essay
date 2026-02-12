# YouTube Video to Essay Tool

## Overview
A tool that converts YouTube videos into well-structured essays with relevant images.

## Architecture

```
YouTube URL
    |
    ├─► youtube-transcript-api / yt-dlp ──► Raw transcript with timestamps
    |
    ├─► yt-dlp (download video) ──► PySceneDetect ──► Keyframes
    |                                                     |
    |                                     (optional) Vision LLM filter
    |                                         (keep slides/diagrams only)
    |
    └─► Claude API (Strategy 1: Simple Direct)
            |
            ├─ Generate essay from transcript
            └─ Insert relevant images at appropriate points
            |
            ▼
        Markdown essay with embedded images
```

## What's Been Done (Experiments)

### 1. Transcript Extraction (DONE)
- **Method**: yt-dlp with cookies + deno JS runtime
- **Format**: Download as JSON3, then parse to clean text
- **Key insight**: JSON3 format has `aAppend` flag to distinguish rolling subtitle duplicates from primary text. Filtering out append events gives clean, non-duplicated transcript.
- **Output**: Timestamped lines and ~30s paragraph-grouped text
- **Files**: `transcript.txt`, `transcript_timestamped.txt`, `raw.en.json3`

### 2. Essay Generation (DONE)
- **Tested 5 strategies** using Claude Sonnet 4.5:
  1. **Simple Direct** — minimal prompt, scored 8.5/10 on coverage ← SELECTED
  2. **CO-STAR Structured** — Economist-style, scored 7.5/10
  3. **Two-Pass Outline-First** — outline then essay, scored 7.5/10, 2x cost
  4. **Financial Journalist** — Bloomberg-style news article, scored 7/10, most concise
  5. **Analytical Brief** — structured with data table, scored 8/10
- **Winner**: Strategy 1 (Simple Direct) — best information coverage with zero prompt engineering overhead
- **Common issues found across all strategies**:
  - All add embellishments not in transcript (e.g., "€" symbol, first names)
  - All lose conversational hedging/uncertainty markers
  - All miss minor details like Nvidia not reacting to Amazon capex news

### 3. Image/Frame Extraction (PARTIALLY DONE)
- **YouTube thumbnails**: Downloaded successfully (4 images) but only show talking head + title card — not useful
- **Video download**: Blocked by YouTube bot detection from cloud IPs
- **Cookies**: Work initially but get rotated by YouTube after use from different IP
- **Installed**: PySceneDetect, ffmpeg, deno — ready to process video once downloaded

## What Still Needs to Be Done

### Phase 1: Core Tool (MVP)
- [ ] **Build the CLI tool** — Python script that takes a YouTube URL and outputs a markdown essay
  - [ ] Accept YouTube URL as argument
  - [ ] Extract transcript (youtube-transcript-api primary, yt-dlp fallback)
  - [ ] Parse JSON3/SRT into clean text
  - [ ] Send to Claude API with Strategy 1 prompt
  - [ ] Output as markdown file
  - [ ] Handle errors gracefully (no transcript available, API failures, etc.)

### Phase 2: Image Extraction
- [ ] **Download video** (requires cookies or running on non-cloud IP)
  - [ ] Cookie management: accept cookies file path as argument
  - [ ] Fallback: skip images if video download fails
- [ ] **Scene detection** with PySceneDetect (ContentDetector)
  - [ ] Extract keyframes at scene transitions
  - [ ] Filter out talking-head frames (blur detection, similarity dedup)
- [ ] **Map frames to transcript timestamps**
  - [ ] Each frame has a timestamp from scene detection
  - [ ] Match to nearest paragraph in essay
- [ ] **Optional**: Vision LLM filter to classify frames (chart/diagram/slide vs talking head)

### Phase 3: Polish
- [ ] **Improve transcript cleaning** — handle edge cases in JSON3 parsing
- [ ] **Add coverage check** — automated comparison of essay vs transcript
- [ ] **Multiple output formats** — markdown, HTML, PDF
- [ ] **Configurable essay style** — let user pick strategy (1-5)
- [ ] **Progress indicators** — show download/processing status
- [ ] **Cost estimation** — show estimated API cost before running

## Dependencies
- `yt-dlp` — video/subtitle download
- `youtube-transcript-api` — transcript extraction (no video download needed)
- `anthropic` — Claude API for essay generation
- `scenedetect` + `opencv-python` — scene detection and frame extraction
- `ffmpeg` — required by yt-dlp and scenedetect
- `deno` — JS runtime required by yt-dlp for YouTube

## Environment Notes
- YouTube blocks cloud provider IPs for both video download and transcript extraction
- Cookies expire quickly when used from a different IP than where they were generated
- For production use, consider: residential proxy, Cloudflare WARP, or running locally
- yt-dlp needs `--remote-components ejs:github` flag for JS challenge solving
