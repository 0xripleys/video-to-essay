# S3 Storage Migration Design

Move the `runs/` directory from local filesystem to AWS S3 for production. Workers process files locally, then sync to S3. Consumers (deliver worker, web API, email) read from S3.

## Approach

Process locally, sync to S3 after each worker step. No changes to the CLI — S3 is a production/worker concern only.

## New Module: `src/video_to_essay/s3.py`

A small module with these functions:

- **`get_s3_client()`** — Cached boto3 S3 client, configured from env vars.
- **`upload_run(video_id: str, step_dirs: list[str] | None = None)`** — Uploads `runs/<video_id>/` tree (or specific step subdirectories) to S3 under key prefix `runs/<video_id>/`.
- **`download_file(video_id: str, relative_path: str) -> bytes`** — Downloads a single file from S3 by key.
- **`download_run(video_id: str, step_dirs: list[str] | None = None)`** — Downloads an entire run (or specific steps) to local disk.

### S3 Key Structure

Mirrors the local directory structure:

```
runs/<video_id>/00_download/video.mp4
runs/<video_id>/00_download/metadata.json
runs/<video_id>/01_transcript/transcript.txt
...
runs/<video_id>/04_frames/kept/frame_0001.jpg
runs/<video_id>/05_place_images/essay_final.md
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `S3_BUCKET_NAME` | Required. Target bucket name. |
| `AWS_ACCESS_KEY_ID` | Standard boto3 auth |
| `AWS_SECRET_ACCESS_KEY` | Standard boto3 auth |
| `AWS_REGION` | Bucket region |

## Worker Changes

### Download Worker (`download_worker.py`)

After downloading video + saving metadata:
```
upload_run(video_id, step_dirs=["00_download"])
```

### Process Worker (`process_worker.py`)

Before processing — pull video from S3 (may have been downloaded on a different machine):
```
download_run(video_id, step_dirs=["00_download"])
```

After processing completes — upload all output steps:
```
upload_run(video_id, step_dirs=["01_transcript", "02_filter_sponsors", "03_essay", "04_frames", "05_place_images"])
```

Additionally, after uploading kept frames to S3, rewrite image paths in `essay_final.md` from relative paths to public S3 URLs before uploading the essay:
- From: `../04_frames/kept/frame_0001.jpg`
- To: `https://<bucket>.s3.<region>.amazonaws.com/runs/<video_id>/04_frames/kept/frame_0001.jpg`

The local copy retains relative paths (still works for CLI). The S3 copy gets rewritten URLs.

### Deliver Worker (`deliver_worker.py`)

Replace the `_get_essay()` function to read from S3:
- `download_file(video_id, "05_place_images/essay_final.md")`
- Fallback: `download_file(video_id, "03_essay/essay.md")`

Since `essay_final.md` on S3 already has public S3 image URLs, emails render images correctly with no embedding step.

### Discover Worker

No changes — no file I/O.

## Web API Changes

### Next.js API Route (`web/app/api/videos/[videoId]/route.ts`)

- Add `@aws-sdk/client-s3` as a web dependency.
- Replace local filesystem reads with S3 `GetObject` calls.
- Fetch `runs/<video_id>/05_place_images/essay_final.md` from S3 (fallback `03_essay/essay.md`).
- No image-serving route needed — images in the markdown are public S3 URLs.

## CLI

No changes. The CLI runs everything locally on one machine. S3 sync is a production/worker concern only. The `--embed` flag remains available for local base64 embedding.

## S3 Bucket Configuration

- Bucket policy: **public-read** for objects under `runs/*/04_frames/kept/` (frame images served in essays and emails).
- All other objects are private (accessed via boto3 credentials).

## What This Does NOT Change

- Pipeline step logic (download, transcript, filter, essay, frames, place_images) — all unchanged.
- Local file I/O patterns — workers still use `pathlib.Path` for processing.
- Database schema — no changes.
- CLI behavior — no changes.
- The `--force` and `--embed` flags — unchanged, CLI-only.
