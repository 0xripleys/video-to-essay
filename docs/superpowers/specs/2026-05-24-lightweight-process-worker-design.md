# Lightweight Process Worker Design

## Goal

Move heavyweight local media work out of the process worker so it can run in a lighter cloud environment. The download worker should own YouTube download and all ffmpeg work. The process worker should consume prepared artifacts from S3 and run API/LLM-oriented processing.

The download worker should only write and upload the `00_download/` prefix. Prepared audio and raw sampled frames will live under that prefix.

## Current Behavior

The current process worker downloads `00_download/` from S3, finds `video.*`, and uses it for two local ffmpeg operations:

- `diarize.extract_audio(...)` writes `01_transcript/audio.mp3`.
- `extract_frames.sample_frames(...)` writes `04_frames/raw/frame_*.jpg`.

The process worker then uses transcript text and sponsor ranges to deduplicate, classify, filter, keep frames, place images, and upload `04_frames/` and later outputs.

## Handoff Layout

For new download-worker runs, `00_download/` becomes the complete media-prep handoff:

```text
runs/<video_id>/
  00_download/
    metadata.json
    audio.mp3
    raw_frames/
      frame_0001.jpg
      frame_0002.jpg
      ...
```

The source `video.*` file is still needed locally by the download worker while preparing the bundle. It should not be uploaded to S3 for new worker runs, and it should not be required by the process worker.

`downloaded_at` should be set only after the download worker has created and uploaded the prepared `00_download/` bundle. If YouTube download, audio extraction, or raw frame sampling fails, the video row should be marked failed as a download-stage failure.

## Worker Responsibilities

### Download Worker

The download worker owns:

- YouTube download via `yt-dlp`.
- Metadata fetch and `00_download/metadata.json`.
- Audio extraction to `00_download/audio.mp3`.
- Raw frame sampling to `00_download/raw_frames/frame_*.jpg`.
- Uploading only the `00_download/` handoff artifacts needed downstream.
- Marking the video downloaded after the handoff is complete.

The download worker should remain idempotent. Existing valid media-prep outputs should be reused unless the local source video is invalid or a force-style path is added later.

### Process Worker

The process worker owns:

- Downloading the prepared `00_download/` handoff from S3.
- Deepgram transcription from `00_download/audio.mp3`.
- Sponsor filtering.
- Essay generation and summarization.
- Frame deduplication, transcript/sponsor-aware filtering, vision classification, and `04_frames/kept/`.
- Image placement, annotation, public S3 image URL rewriting, and final upload.

The process worker should not need ffmpeg for new runs. It should not download the source video for new runs.

## Module Changes

Split the current media functions without changing CLI behavior:

- Keep `diarize.extract_audio(video_path, output_dir)` for CLI/local flows.
- Add a transcription entry point that accepts an existing audio file, for example `transcribe_audio_with_deepgram(audio_path, output_dir, metadata, force=False, model=None)`.
- Keep `extract_frames.sample_frames(video_path, output_dir, interval_seconds)` for download-worker and CLI use.
- Add a classification entry point that accepts an existing raw frame directory or frame list, then performs sponsor filtering, pHash deduplication, LLM classification, and kept-frame copying.
- Keep `extract_and_classify(video=..., output_dir=...)` as the CLI-compatible wrapper that samples into `04_frames/raw/` before classifying.

This keeps the command-line pipeline behavior stable while letting workers use the lighter split.

## S3 Download Behavior

For new runs, the download worker should upload `metadata.json`, `audio.mp3`, and `raw_frames/**` under `00_download/`, excluding source `video.*`. With that contract, the process worker can safely download the full `00_download/` prefix without pulling a large video file.

If a compatibility fallback for older S3 runs is kept, it should be explicit: when the prepared bundle is missing, the process worker may download legacy `video.*` and do local ffmpeg only in environments that still support it. The cloud process deployment should rely on prepared bundles and should not need ffmpeg.

## Backward Compatibility

Existing CLI commands should keep the same visible behavior:

- `video-to-essay run` still downloads a video, extracts audio, samples frames, and writes the traditional step outputs.
- `video-to-essay transcript` still works from a downloaded video.
- `video-to-essay extract-frames` still works from a downloaded video and writes `04_frames/raw/`.

For worker processing, old already-downloaded S3 runs may lack `00_download/audio.mp3` and `00_download/raw_frames/`. In the cloud deployment, those rows should fail with a clear "prepared download bundle missing" message or be re-run through the download worker. Local process-worker environments may keep a legacy fallback while the migration is in progress.

## Testing

Add focused tests for:

- Download worker creates `audio.mp3` and `raw_frames/` before marking downloaded.
- Download worker upload excludes or does not require source `video.*` in the handoff path.
- Process worker transcribes from `00_download/audio.mp3` without calling `extract_audio`.
- Process worker classifies from `00_download/raw_frames/` without calling `sample_frames`.
- Existing CLI wrapper tests still pass for local full-pipeline behavior.

Run:

```bash
uv run pytest tests/test_process_worker.py -x
uv run pytest tests/db/test_download_worker.py tests/db/test_process_worker.py -x
uv run pytest tests/test_extract_frames.py tests/test_pipeline_chain.py -x
uv run ruff check
```
