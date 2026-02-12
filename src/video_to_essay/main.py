"""
Video-to-Essay pipeline — single entry point for all steps.

Usage:
    python main.py run <url>                    # Full pipeline
    python main.py transcript <url>             # Extract transcript only
    python main.py essay <video_id>             # Generate essay from transcript
    python main.py download <video_id>          # Download video
    python main.py extract-frames <video_id>    # Extract + classify frames
    python main.py place-images <video_id>      # Place images + annotate
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from .extract_frames import extract_and_classify, parse_transcript
from .place_images import (
    annotate_essay,
    embed_images,
    load_kept_frames,
    place_images_in_essay,
)
from .transcriber import download_video, extract_video_id, fetch_transcript, transcript_to_essay

RUNS_DIR = Path("runs")

app = typer.Typer(help="Convert YouTube videos into illustrated essays.")


def _run_dir(video_id: str) -> Path:
    """Return and create the run directory for a video."""
    d = RUNS_DIR / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(run_dir: Path, url: str, video_id: str) -> None:
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "url": url,
            "video_id": video_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))


# ---------------------------------------------------------------------------
# Step functions — each returns True on success
# ---------------------------------------------------------------------------

def _step_transcript(
    video_id: str, run_dir: Path, cookies: str | None, force: bool
) -> bool:
    out = run_dir / "transcript.txt"
    if out.exists() and not force:
        print(f"Transcript exists, skipping ({out})")
        return True
    try:
        text = fetch_transcript(video_id, cookies)
        out.write_text(text)
        print(f"Transcript saved ({len(text)} chars) -> {out}")
        return True
    except Exception as e:
        print(f"ERROR in transcript step: {e}")
        return False


def _step_essay(video_id: str, run_dir: Path, force: bool) -> bool:
    transcript_path = run_dir / "transcript.txt"
    out = run_dir / "essay.md"
    if out.exists() and not force:
        print(f"Essay exists, skipping ({out})")
        return True
    if not transcript_path.exists():
        print(f"ERROR: {transcript_path} not found — run transcript step first")
        return False
    try:
        text = transcript_to_essay(transcript_path.read_text())
        out.write_text(text)
        print(f"Essay saved ({len(text)} chars) -> {out}")
        return True
    except Exception as e:
        print(f"ERROR in essay step: {e}")
        return False


def _step_download(
    video_id: str, run_dir: Path, cookies: str | None, force: bool
) -> bool:
    out = run_dir / "video.mp4"
    # Check for any video file (yt-dlp may use different extensions)
    existing = sorted(run_dir.glob("video.*"))
    if existing and not force:
        print(f"Video exists, skipping ({existing[0]})")
        return True
    try:
        actual = download_video(video_id, out, cookies)
        print(f"Video saved -> {actual}")
        return True
    except Exception as e:
        print(f"ERROR in download step: {e}")
        return False


def _step_extract_frames(video_id: str, run_dir: Path, force: bool) -> bool:
    frames_dir = run_dir / "frames"
    kept_dir = frames_dir / "kept"
    if kept_dir.exists() and any(kept_dir.iterdir()) and not force:
        print(f"Frames exist, skipping ({kept_dir})")
        return True

    # Find the video file (may be .mp4, .webm, etc.)
    video_files = sorted(run_dir.glob("video.*"))
    if not video_files:
        print(f"ERROR: No video file in {run_dir} — run download step first")
        return False
    video_path = video_files[0]

    # Load transcript for context if available
    transcript_entries: list[tuple[int, str]] | None = None
    transcript_path = run_dir / "transcript.txt"
    if transcript_path.exists():
        transcript_entries = parse_transcript(transcript_path.read_text())
        print(f"Using transcript context ({len(transcript_entries)} lines)")

    try:
        extract_and_classify(
            video=video_path,
            output_dir=frames_dir,
            transcript_entries=transcript_entries,
        )
        return True
    except Exception as e:
        print(f"ERROR in extract-frames step: {e}")
        return False


def _step_place_images(
    video_id: str, run_dir: Path, embed: bool, force: bool
) -> bool:
    essay_path = run_dir / "essay.md"
    frames_dir = run_dir / "frames"
    out_placed = run_dir / "essay_with_images.md"
    out_final = run_dir / "essay_final.md"

    if out_final.exists() and not force:
        print(f"Final essay exists, skipping ({out_final})")
        return True
    if not essay_path.exists():
        print(f"ERROR: {essay_path} not found — run essay step first")
        return False
    if not (frames_dir / "kept").exists():
        print(f"ERROR: {frames_dir / 'kept'} not found — run extract-frames step first")
        return False

    try:
        essay_text = essay_path.read_text()
        kept = load_kept_frames(frames_dir)

        if not kept:
            print("WARNING: No kept frames found. Copying essay as final.")
            out_placed.write_text(essay_text)
            out_final.write_text(essay_text)
            return True

        # Place images
        with_images = place_images_in_essay(essay_text, kept)
        out_placed.write_text(with_images)
        print(f"Essay with images -> {out_placed}")

        # Annotate figures
        annotated = annotate_essay(with_images)
        if embed:
            annotated = embed_images(annotated, frames_dir)
            print("Embedded images as base64 data URIs")
        out_final.write_text(annotated)
        print(f"Final essay -> {out_final}")
        return True
    except Exception as e:
        print(f"ERROR in place-images step: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

@app.command()
def run(
    url: str = typer.Argument(..., help="YouTube video URL"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Re-run all steps even if outputs exist"),
    embed: bool = typer.Option(True, "--embed/--no-embed", help="Embed images as base64 data URIs"),
) -> None:
    """Run the full pipeline: transcript -> essay -> download -> frames -> place images."""
    video_id = extract_video_id(url)
    run_dir = _run_dir(video_id)
    _save_metadata(run_dir, url, video_id)
    print(f"Video ID: {video_id}")
    print(f"Run dir:  {run_dir}\n")

    steps: list[tuple[str, bool]] = []

    print("=" * 60)
    print("Step 1/6: Transcript")
    print("=" * 60)
    ok = _step_transcript(video_id, run_dir, cookies, force)
    steps.append(("transcript", ok))
    if not ok:
        print("\nPipeline stopped at transcript step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 2/6: Essay")
    print("=" * 60)
    ok = _step_essay(video_id, run_dir, force)
    steps.append(("essay", ok))
    if not ok:
        print("\nPipeline stopped at essay step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 3/6: Download video")
    print("=" * 60)
    ok = _step_download(video_id, run_dir, cookies, force)
    steps.append(("download", ok))
    if not ok:
        print("\nPipeline stopped at download step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 4/6: Extract frames")
    print("=" * 60)
    ok = _step_extract_frames(video_id, run_dir, force)
    steps.append(("extract-frames", ok))
    if not ok:
        print("\nPipeline stopped at extract-frames step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 5-6/6: Place images + annotate")
    print("=" * 60)
    ok = _step_place_images(video_id, run_dir, embed, force)
    steps.append(("place-images", ok))
    if not ok:
        print("\nPipeline stopped at place-images step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Done!")
    print("=" * 60)
    print(f"Final essay: {run_dir / 'essay_final.md'}")


@app.command()
def transcript(
    url: str = typer.Argument(..., help="YouTube video URL"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing transcript"),
) -> None:
    """Extract transcript only."""
    video_id = extract_video_id(url)
    run_dir = _run_dir(video_id)
    _save_metadata(run_dir, url, video_id)
    print(f"Video ID: {video_id}")

    if not _step_transcript(video_id, run_dir, cookies, force):
        raise typer.Exit(1)


@app.command()
def essay(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing essay"),
) -> None:
    """Generate essay from existing transcript."""
    run_dir = _run_dir(video_id)
    if not _step_essay(video_id, run_dir, force):
        raise typer.Exit(1)


@app.command()
def download(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing video"),
) -> None:
    """Download video only."""
    run_dir = _run_dir(video_id)
    if not _step_download(video_id, run_dir, cookies, force):
        raise typer.Exit(1)


@app.command("extract-frames")
def extract_frames_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    force: bool = typer.Option(False, "--force", help="Re-extract frames"),
) -> None:
    """Extract and classify frames from existing video."""
    run_dir = _run_dir(video_id)
    if not _step_extract_frames(video_id, run_dir, force):
        raise typer.Exit(1)


@app.command("place-images")
def place_images_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    embed: bool = typer.Option(True, "--embed/--no-embed", help="Embed images as base64 data URIs"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
) -> None:
    """Place images and annotate figures in existing essay."""
    run_dir = _run_dir(video_id)
    if not _step_place_images(video_id, run_dir, embed, force):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
