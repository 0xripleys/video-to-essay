# Lightweight Process Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Move ffmpeg audio extraction and raw frame sampling into the download worker while keeping all prepared media under `00_download/`.

**Architecture:** The download worker will create a prepared handoff bundle at `00_download/metadata.json`, `00_download/audio.mp3`, and `00_download/raw_frames/*.jpg`, then upload that prefix without source `video.*` files. The process worker will consume that prepared bundle, run Deepgram/LLM processing, classify from existing raw frames, and continue writing downstream artifacts to `01_transcript/` through `05_place_images/`.

**Tech Stack:** Python 3.14, Typer, pytest, boto3 S3 helpers, ffmpeg, Deepgram, LiteLLM/OpenRouter, Next.js runs viewer.

---

### Task 1: Split Media Helpers

**Files:**
- Modify: `src/video_to_essay/diarize.py`
- Modify: `src/video_to_essay/extract_frames.py`
- Test: `tests/test_extract_frames.py`

- [x] **Step 1: Add a test for classifying existing raw frames**

Add a test that seeds `raw_frames/frame_0001.jpg` and `raw_frames/frame_0002.jpg`, calls `classify_sampled_frames(raw_frames_dir=raw_dir, output_dir=out_dir)`, and asserts `classifications.json` is written and only the useful frame is copied to `04_frames/kept/`.

Run: `uv run pytest tests/test_extract_frames.py::test_classify_sampled_frames_writes_kept_from_raw_dir -q`

Expected: FAIL because `classify_sampled_frames` does not exist.

- [x] **Step 2: Add `transcribe_audio_with_deepgram`**

In `src/video_to_essay/diarize.py`, move the Deepgram diarization, speaker mapping, and transcript writing body into:

```python
def transcribe_audio_with_deepgram(
    audio_path: Path,
    output_dir: Path,
    metadata: dict,
    force: bool = False,
    model: str | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = output_dir / "transcript.txt"
    if not force and transcript_path.exists():
        logger.info("Transcript exists, skipping (%s)", transcript_path)
        return
    if not audio_path.exists():
        raise FileNotFoundError(f"Prepared audio file not found: {audio_path}")
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not set. Set it in .env or environment. Get a free key at https://console.deepgram.com/signup")
    segments = run_diarization(audio_path, api_key, output_dir)
    unique_speakers = set(s["speaker"] for s in segments)
    speaker_names = map_speaker_names(segments, metadata, output_dir, model=model) if len(unique_speakers) > 1 else None
    transcript_path.write_text(format_transcript(segments, speaker_names))
```

Keep `transcribe_with_deepgram(video_path, output_dir, metadata, force=False, model=None)` as a wrapper that skips when `transcript.txt` exists, extracts audio from the video into the transcript output dir, then calls `transcribe_audio_with_deepgram(audio_path, output_dir, metadata, force=force, model=model)`.

- [x] **Step 3: Add `classify_sampled_frames`**

In `src/video_to_essay/extract_frames.py`, add:

```python
def classify_sampled_frames(
    raw_frames_dir: Path,
    output_dir: Path,
    interval: int = 5,
    transcript_entries: list[tuple[int, str]] | None = None,
    max_hamming: int = 8,
    min_value: int = 3,
    skip_categories: set[str] | None = None,
    sponsor_ranges: list[tuple[int, int]] | None = None,
    model: str | None = None,
) -> list[dict[str, str | int]]:
    if skip_categories is None:
        skip_categories = {"talking_head", "transition", "advertisement"}
    frames = sorted(raw_frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError(f"No raw frame samples found in {raw_frames_dir}")
    return []
```

It should read `frame_*.jpg` from `raw_frames_dir`, drop frames in sponsor ranges, deduplicate, classify, copy kept frames to `output_dir / "kept"`, write `output_dir / "classifications.json"`, and return kept classifications.

Refactor `extract_and_classify(video=video_path, output_dir=frames_dir)` so it samples to `output_dir / "raw"` and then delegates to `classify_sampled_frames(raw_frames_dir=raw_dir, output_dir=output_dir)`.

- [x] **Step 4: Verify helper tests pass**

Run: `uv run pytest tests/test_extract_frames.py -q`

Expected: PASS.

### Task 2: Prepare Media in Download Worker

**Files:**
- Modify: `src/video_to_essay/download_worker.py`
- Modify: `src/video_to_essay/s3.py`
- Test: `tests/db/test_download_worker.py`

- [x] **Step 1: Update download-worker tests first**

Update `tests/db/test_download_worker.py` so mocked `download_video(video_id, run_dir)` creates `00_download/video.mp4`, mocked `extract_audio(video_path, run_dir)` writes `00_download/audio.mp3`, and mocked `sample_frames(video_path, raw_frames_dir, interval_seconds)` writes `00_download/raw_frames/frame_0001.jpg`. Assert `upload_run(video_id, step_dirs=["00_download"], exclude_globs=["00_download/video.*"])` is called.

Run: `uv run pytest tests/db/test_download_worker.py -q`

Expected: FAIL because the worker does not prepare audio/raw frames or pass `exclude_globs`.

- [x] **Step 2: Add upload exclusion support**

In `src/video_to_essay/s3.py`, extend `upload_run`:

```python
def upload_run(
    video_id: str,
    step_dirs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> None:
    client = get_s3_client()
    bucket, _ = _get_config()
    base = RUNS_DIR / video_id
    rel_path = file_path.relative_to(base)
    if exclude_globs and any(rel_path.match(pattern) for pattern in exclude_globs):
        continue
```

Existing callers keep working because `exclude_globs` defaults to `None`.

- [x] **Step 3: Add download media prep**

In `src/video_to_essay/download_worker.py`, import `extract_audio` and `sample_frames`. After video download/validation and metadata writing, call a helper that writes:

```text
00_download/audio.mp3
00_download/raw_frames/frame_*.jpg
```

The raw-frame helper should skip if `raw_frames/frame_*.jpg` already exists, and should raise if sampling produces no frames.

- [x] **Step 4: Exclude source video from S3 upload**

Change the worker upload call to:

```python
upload_run(video_id, step_dirs=["00_download"], exclude_globs=["00_download/video.*"])
```

- [x] **Step 5: Verify download tests pass**

Run: `uv run pytest tests/db/test_download_worker.py -q`

Expected: PASS.

### Task 3: Consume Prepared Bundle in Process Worker

**Files:**
- Modify: `src/video_to_essay/process_worker.py`
- Test: `tests/test_process_worker.py`
- Test: `tests/db/test_process_worker.py`

- [x] **Step 1: Update process-worker tests first**

Change process-worker tests to seed `00_download/audio.mp3` and `00_download/raw_frames/frame_0001.jpg`, patch `transcribe_audio_with_deepgram`, patch `classify_sampled_frames`, and assert the worker passes the prepared audio and raw frame directory rather than a video path.

Run: `uv run pytest tests/test_process_worker.py tests/db/test_process_worker.py -q`

Expected: FAIL because process worker still uses `video.*`, `transcribe_with_deepgram`, and `extract_and_classify`.

- [x] **Step 2: Update process worker imports**

Replace process-worker imports:

```python
from .diarize import transcribe_audio_with_deepgram
from .extract_frames import classify_sampled_frames, parse_transcript
```

- [x] **Step 3: Remove source-video dependency**

After `download_run(youtube_video_id, step_dirs=["00_download"])`, load:

```python
audio_path = dl_dir / "audio.mp3"
raw_frames_dir = dl_dir / "raw_frames"
```

Call `transcribe_audio_with_deepgram(audio_path, transcript_dir, meta, force=False)`. Before classifying frames, require `raw_frames_dir` to exist and contain at least one `frame_*.jpg`, then call `classify_sampled_frames(raw_frames_dir=raw_frames_dir, output_dir=frames_dir, transcript_entries=transcript_entries, sponsor_ranges=sponsor_ranges)`.

- [x] **Step 4: Verify process tests pass**

Run: `uv run pytest tests/test_process_worker.py tests/db/test_process_worker.py -q`

Expected: PASS.

### Task 4: Keep Runs Viewer and Docs Aligned

**Files:**
- Modify: `web/app/runs/[videoId]/page.tsx`
- Modify: `web/app/runs/[videoId]/RunDetail.tsx`
- Modify: `web/app/runs/[videoId]/tabs/Frames.tsx`
- Modify: `docs/architecture-workers-and-database.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Route frame thumbnails to the right prefix**

Compute a raw frame prefix from listed files:

```ts
const rawFramePrefix = files.some((f) => f.relativePath.startsWith("00_download/raw_frames/"))
  ? "00_download/raw_frames"
  : "04_frames/raw";
```

Pass it to `Frames`, and use it in `frameUrl(videoId, rawFramePrefix, frameName)`.

- [x] **Step 2: Update architecture docs**

Document that the download worker creates `00_download/audio.mp3` and `00_download/raw_frames/`, excludes source `video.*` from S3 uploads for new runs, and the process worker consumes prepared media.

- [x] **Step 3: Verify TypeScript syntax**

Run: `cd web && npm run lint`

Expected: PASS, or report if the repo has no configured lint command.

### Task 5: Full Verification

**Files:**
- Validate touched Python and web files.

- [x] **Step 1: Run focused Python tests**

Run:

```bash
uv run pytest tests/test_extract_frames.py tests/test_process_worker.py tests/db/test_download_worker.py tests/db/test_process_worker.py tests/test_pipeline_chain.py -q
```

Expected: PASS.

- [x] **Step 2: Run lint**

Run:

```bash
uv run ruff check
```

Expected: PASS.

- [x] **Step 3: Inspect diff**

Run:

```bash
git diff --stat
git diff -- src/video_to_essay/diarize.py src/video_to_essay/extract_frames.py src/video_to_essay/download_worker.py src/video_to_essay/process_worker.py src/video_to_essay/s3.py
```

Expected: Diff matches the approved `00_download/` handoff design and does not include unrelated changes.
