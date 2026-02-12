"""
Experiment: Fixed-interval sampling + hash dedup + Vision LLM classification.

Extracts useful frames from a video for essay illustration.

Pipeline:
  1. Sample 1 frame every N seconds using ffmpeg
  2. Perceptual hash dedup (pHash) to collapse near-identical frames
  3. Send unique frames to Claude Haiku for classification and relevance scoring
  4. Keep only frames rated as useful
"""

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import anthropic
import cv2
import imagehash
import typer
from PIL import Image

app = typer.Typer()


def parse_transcript(transcript: str) -> list[tuple[int, str]]:
    """Parse timestamped transcript into list of (seconds, text) tuples."""
    entries: list[tuple[int, str]] = []
    for line in transcript.strip().splitlines():
        match = re.match(r"\[(\d{2}):(\d{2})\]\s*(.*)", line)
        if match:
            seconds = int(match.group(1)) * 60 + int(match.group(2))
            entries.append((seconds, match.group(3)))
    return entries


def get_transcript_context(
    frame_seconds: int, transcript_entries: list[tuple[int, str]], window: int = 15
) -> str:
    """Get transcript text within +/- window seconds of a frame timestamp."""
    lines: list[str] = []
    for ts, text in transcript_entries:
        if abs(ts - frame_seconds) <= window:
            lines.append(text)
    return " ".join(lines) if lines else ""


def sample_frames(
    video_path: Path, output_dir: Path, interval_seconds: int
) -> list[Path]:
    """Extract 1 frame every `interval_seconds` using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%04d.jpg"

    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_seconds}",
        "-q:v",
        "2",  # high quality JPEG
        str(pattern),
        "-y",
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    frames = sorted(output_dir.glob("frame_*.jpg"))
    return frames


def compute_hashes(frames: list[Path]) -> dict[Path, imagehash.ImageHash]:
    """Compute perceptual hash for each frame."""
    hashes: dict[Path, imagehash.ImageHash] = {}
    for frame_path in frames:
        img = Image.open(frame_path)
        hashes[frame_path] = imagehash.phash(img)
    return hashes


def laplacian_variance(frame_path: Path) -> float:
    """Compute Laplacian variance (edge density / sharpness)."""
    img = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
    return cv2.Laplacian(img, cv2.CV_64F).var()


def dedup_frames(
    frames: list[Path],
    hashes: dict[Path, imagehash.ImageHash],
    max_hamming_distance: int = 8,
) -> list[Path]:
    """Cluster frames by hash similarity, keep sharpest from each cluster."""
    clusters: list[list[Path]] = []

    for frame in frames:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            distance = hashes[frame] - hashes[representative]
            if distance <= max_hamming_distance:
                cluster.append(frame)
                placed = True
                break
        if not placed:
            clusters.append([frame])

    # From each cluster, keep the frame with highest Laplacian variance
    kept: list[Path] = []
    for cluster in clusters:
        best = max(cluster, key=laplacian_variance)
        kept.append(best)

    return kept


def encode_image_base64(frame_path: Path) -> str:
    """Read an image file and return base64-encoded string."""
    return base64.standard_b64encode(frame_path.read_bytes()).decode("utf-8")


def frame_seconds(frame_path: Path, interval_seconds: int) -> int:
    """Derive the approximate timestamp in seconds from the frame filename."""
    num = int(frame_path.stem.split("_")[1])
    return (num - 1) * interval_seconds


def frame_timestamp(frame_path: Path, interval_seconds: int) -> str:
    """Derive the approximate timestamp from the frame filename."""
    total_sec = frame_seconds(frame_path, interval_seconds)
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes:02d}:{seconds:02d}"


def classify_frames(
    frames: list[Path],
    interval_seconds: int,
    transcript_entries: list[tuple[int, str]] | None = None,
) -> list[dict[str, str | int]]:
    """Send frames to Claude Haiku for classification and relevance scoring."""
    client = anthropic.Anthropic()

    results: list[dict[str, str | int]] = []

    for frame_path in frames:
        timestamp = frame_timestamp(frame_path, interval_seconds)
        b64 = encode_image_base64(frame_path)

        # Get nearby transcript context
        frame_sec = frame_seconds(frame_path, interval_seconds)
        context = ""
        if transcript_entries:
            context = get_transcript_context(frame_sec, transcript_entries)

        context_block = ""
        if context:
            context_block = (
                f"\n\nThe speaker is saying around this timestamp ({timestamp}):\n"
                f'"{context}"'
            )

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Classify this video frame. Respond with ONLY valid JSON, no other text.\n\n"
                                "{\n"
                                '  "category": one of "slide", "chart", "code", "diagram", "key_moment", "talking_head", "transition", "other",\n'
                                '  "value": 1-5 (5 = essential visual information for an essay about this video),\n'
                                '  "description": brief description of what the frame shows and how it relates to what is being discussed\n'
                                "}"
                                f"{context_block}"
                            ),
                        },
                    ],
                }
            ],
        )

        raw = msg.content[0].text.strip()
        # Handle markdown code blocks
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"category": "unknown", "value": 0, "description": raw}

        parsed["frame"] = frame_path.name
        parsed["timestamp"] = timestamp
        parsed["file"] = str(frame_path)
        results.append(parsed)

        typer.echo(
            f"  [{timestamp}] {frame_path.name}: "
            f"{parsed.get('category', '?')} (value={parsed.get('value', '?')}) "
            f"- {parsed.get('description', '')[:80]}"
        )

    return results


@app.command()
def extract(
    video: Path = typer.Argument(..., help="Path to video file"),
    output_dir: Path = typer.Option(
        Path("frames"), "--output", "-o", help="Output directory for frames"
    ),
    interval: int = typer.Option(
        5, "--interval", "-i", help="Seconds between frame samples"
    ),
    max_hamming: int = typer.Option(
        8, "--max-hamming", help="Max Hamming distance for dedup clustering"
    ),
    min_value: int = typer.Option(
        3, "--min-value", help="Minimum LLM value score to keep a frame (1-5)"
    ),
    skip_categories: str = typer.Option(
        "talking_head,transition",
        "--skip",
        help="Comma-separated categories to discard",
    ),
    transcript: Path | None = typer.Option(
        None, "--transcript", "-t", help="Transcript file with [MM:SS] timestamps"
    ),
    video_id: str | None = typer.Option(
        None, "--video-id", help="YouTube video ID to auto-fetch transcript"
    ),
) -> None:
    """Extract useful frames from a video using vision LLM classification."""
    if not video.exists():
        typer.echo(f"Error: {video} not found", err=True)
        raise typer.Exit(1)

    skip_set = {c.strip() for c in skip_categories.split(",")}

    # Load or fetch transcript
    transcript_entries: list[tuple[int, str]] | None = None
    if transcript:
        typer.echo(f"Loading transcript from {transcript}...")
        transcript_entries = parse_transcript(transcript.read_text())
        typer.echo(f"  {len(transcript_entries)} lines loaded")
    elif video_id:
        typer.echo(f"Fetching transcript for {video_id}...")
        from transcriber import fetch_transcript

        raw = fetch_transcript(video_id)
        transcript_entries = parse_transcript(raw)
        typer.echo(f"  {len(transcript_entries)} lines loaded")

    # Step 1: Sample frames
    raw_dir = output_dir / "raw"
    typer.echo(f"Step 1: Sampling 1 frame every {interval}s...")
    frames = sample_frames(video, raw_dir, interval)
    typer.echo(f"  Extracted {len(frames)} frames")

    # Step 2: Dedup
    typer.echo(f"Step 2: Deduplicating (max Hamming distance={max_hamming})...")
    hashes = compute_hashes(frames)
    unique_frames = dedup_frames(frames, hashes, max_hamming)
    typer.echo(f"  {len(frames)} → {len(unique_frames)} unique frames")

    # Step 3: Classify with vision LLM
    typer.echo(f"Step 3: Classifying {len(unique_frames)} frames with Claude Haiku...")
    classifications = classify_frames(unique_frames, interval, transcript_entries)

    # Step 4: Filter
    typer.echo(f"\nStep 4: Filtering (min_value={min_value}, skip={skip_set})...")
    kept: list[dict[str, str | int]] = []
    for c in classifications:
        if c.get("category") in skip_set:
            continue
        if c.get("value", 0) >= min_value:
            kept.append(c)

    # Copy kept frames to output dir
    kept_dir = output_dir / "kept"
    kept_dir.mkdir(parents=True, exist_ok=True)
    for item in kept:
        src = Path(str(item["file"]))
        dst = kept_dir / src.name
        dst.write_bytes(src.read_bytes())

    # Save results
    results_path = output_dir / "classifications.json"
    results_path.write_text(json.dumps(classifications, indent=2))

    typer.echo(f"\nResults:")
    typer.echo(f"  Total sampled:    {len(frames)}")
    typer.echo(f"  After dedup:      {len(unique_frames)}")
    typer.echo(f"  After filtering:  {len(kept)}")
    typer.echo(f"  Kept frames in:   {kept_dir}")
    typer.echo(f"  Full results:     {results_path}")

    if kept:
        typer.echo(f"\nKept frames:")
        for item in kept:
            typer.echo(
                f"  [{item['timestamp']}] {item['frame']}: "
                f"{item['category']} (value={item['value']}) "
                f"- {item.get('description', '')[:80]}"
            )


if __name__ == "__main__":
    app()
