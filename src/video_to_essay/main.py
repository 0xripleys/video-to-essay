"""
Video-to-Essay pipeline — single entry point for all steps.

Usage:
    python main.py run <url>                    # Full pipeline
    python main.py download <video_id>          # Download video
    python main.py transcript <url>             # Download + extract transcript
    python main.py filter-sponsors <video_id>   # Filter sponsor/ad segments
    python main.py essay <video_id>             # Generate essay from transcript
    python main.py extract-frames <video_id>    # Extract + classify frames
    python main.py place-images <video_id>      # Place images + annotate
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import sentry_sdk
import typer

DEFAULT_RUNS_DIR = Path("runs")

from .diarize import transcribe_with_deepgram
from .extract_frames import extract_and_classify, parse_transcript
from .filter_sponsors import filter_sponsors
from .place_images import (
    annotate_essay,
    embed_images,
    load_kept_frames,
    place_images_in_essay,
)
from .scorer import DIMENSION_NAMES, score_essay, score_one  # noqa: F401
from .summarize import summarize_essay
from .transcriber import (
    download_video,
    extract_video_id,
    fetch_video_metadata,
    transcript_to_essay,
)

app = typer.Typer(help="Convert YouTube videos into illustrated essays.")


@app.callback()
def _startup() -> None:
    """Initialize logging and Sentry before any subcommand runs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=1.0,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )

# ---------------------------------------------------------------------------
# Step directory layout
# ---------------------------------------------------------------------------

STEP_DIRS: dict[str, str] = {
    "download": "00_download",
    "transcript": "01_transcript",
    "filter_sponsors": "02_filter_sponsors",
    "essay": "03_essay",
    "frames": "04_frames",
    "place_images": "05_place_images",
}


def _run_dir(video_id: str, output_dir: Path | None = None) -> Path:
    """Return and create the run directory for a video."""
    base = output_dir if output_dir else DEFAULT_RUNS_DIR
    d = base / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _step_dir(run_dir: Path, step: str) -> Path:
    """Return and create the subdirectory for a pipeline step."""
    d = run_dir / STEP_DIRS[step]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(
    run_dir: Path, url: str, video_id: str, cookies: str | None = None
) -> dict:
    """Save and return metadata. Enriches with YouTube metadata via yt-dlp."""
    dl_dir = _step_dir(run_dir, "download")
    meta_path = dl_dir / "metadata.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())

    meta: dict = {
        "url": url,
        "video_id": video_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        yt_meta = fetch_video_metadata(video_id, cookies)
        meta.update(yt_meta)
    except Exception as e:
        print(f"WARNING: Could not fetch video metadata: {e}")

    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


# ---------------------------------------------------------------------------
# Step functions — each returns True on success
# ---------------------------------------------------------------------------

def _step_download(
    video_id: str, run_dir: Path, cookies: str | None, force: bool
) -> bool:
    dl_dir = _step_dir(run_dir, "download")
    existing = sorted(dl_dir.glob("video.*"))
    if existing and not force:
        print(f"Video exists, skipping ({existing[0]})")
        return True
    try:
        actual = download_video(video_id, dl_dir, cookies)
        print(f"Video saved -> {actual}")
        return True
    except Exception as e:
        print(f"ERROR in download step: {e}")
        return False


def _step_transcript(
    run_dir: Path,
    force: bool,
    metadata: dict,
) -> bool:
    dl_dir = _step_dir(run_dir, "download")
    transcript_dir = _step_dir(run_dir, "transcript")

    # Find video in download dir
    video_files = sorted(dl_dir.glob("video.*"))
    if not video_files:
        print(f"ERROR: No video file in {dl_dir} — run download step first")
        return False
    video_path = video_files[0]

    try:
        transcribe_with_deepgram(video_path, transcript_dir, metadata, force)
        return True
    except Exception as e:
        print(f"ERROR in transcript step: {e}")
        return False


def _step_filter_sponsors(video_id: str, run_dir: Path, force: bool) -> bool:
    transcript_dir = _step_dir(run_dir, "transcript")
    filter_dir = _step_dir(run_dir, "filter_sponsors")

    transcript_path = transcript_dir / "transcript.txt"
    clean_path = filter_dir / "transcript_clean.txt"
    segments_path = filter_dir / "sponsor_segments.json"

    if clean_path.exists() and segments_path.exists() and not force:
        print(f"Filtered transcript exists, skipping ({clean_path})")
        return True
    if not transcript_path.exists():
        print("ERROR: no transcript found — run transcript step first")
        return False
    try:
        cleaned, sponsor_ranges = filter_sponsors(transcript_path.read_text())
        clean_path.write_text(cleaned)
        segments_path.write_text(json.dumps(sponsor_ranges, indent=2))
        if sponsor_ranges:
            print(f"Found {len(sponsor_ranges)} sponsor segment(s):")
            for start, end in sponsor_ranges:
                print(f"  {start // 60:02d}:{start % 60:02d} - {end // 60:02d}:{end % 60:02d}")
        else:
            print("No sponsor segments detected")
        print(f"Cleaned transcript -> {clean_path}")
        return True
    except Exception as e:
        print(f"ERROR in filter-sponsors step: {e}")
        return False


def _step_essay(video_id: str, run_dir: Path, force: bool) -> bool:
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    essay_dir = _step_dir(run_dir, "essay")

    transcript_path = filter_dir / "transcript_clean.txt"
    out = essay_dir / "essay.md"

    if out.exists() and not force:
        print(f"Essay exists, skipping ({out})")
        return True
    if not transcript_path.exists():
        print("ERROR: no transcript found — run filter-sponsors step first")
        return False
    try:
        text = transcript_to_essay(transcript_path.read_text(), video_id=video_id)
        out.write_text(text)
        print(f"Essay saved ({len(text)} chars) -> {out}")
        return True
    except Exception as e:
        print(f"ERROR in essay step: {e}")
        return False


def _step_extract_frames(video_id: str, run_dir: Path, force: bool) -> bool:
    dl_dir = _step_dir(run_dir, "download")
    transcript_dir = _step_dir(run_dir, "transcript")
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    frames_dir = _step_dir(run_dir, "frames")

    kept_dir = frames_dir / "kept"
    if kept_dir.exists() and any(kept_dir.iterdir()) and not force:
        print(f"Frames exist, skipping ({kept_dir})")
        return True

    # Find the video file
    video_files = sorted(dl_dir.glob("video.*"))
    if not video_files:
        print(f"ERROR: No video file in {dl_dir} — run download step first")
        return False
    video_path = video_files[0]

    # Load transcript for context
    transcript_path = transcript_dir / "transcript.txt"
    if not transcript_path.exists():
        print(f"ERROR: {transcript_path} not found — run transcript step first")
        return False
    transcript_entries = parse_transcript(transcript_path.read_text())
    print(f"Using transcript context ({len(transcript_entries)} lines)")

    # Load sponsor ranges
    segments_path = filter_dir / "sponsor_segments.json"
    if not segments_path.exists():
        print(f"ERROR: {segments_path} not found — run filter-sponsors step first")
        return False
    raw_ranges = json.loads(segments_path.read_text())
    sponsor_ranges: list[tuple[int, int]] = [(s, e) for s, e in raw_ranges]
    if sponsor_ranges:
        print(f"Using {len(sponsor_ranges)} sponsor range(s) for frame filtering")

    try:
        extract_and_classify(
            video=video_path,
            output_dir=frames_dir,
            transcript_entries=transcript_entries,
            sponsor_ranges=sponsor_ranges,
        )
        return True
    except Exception as e:
        print(f"ERROR in extract-frames step: {e}")
        return False


def _step_place_images(
    video_id: str, run_dir: Path, embed: bool, force: bool
) -> bool:
    essay_dir = _step_dir(run_dir, "essay")
    frames_dir = _step_dir(run_dir, "frames")
    place_dir = _step_dir(run_dir, "place_images")

    essay_path = essay_dir / "essay.md"
    kept_dir = frames_dir / "kept"
    classifications_path = frames_dir / "classifications.json"
    out_placed = place_dir / "essay_with_images.md"
    out_final = place_dir / "essay_final.md"

    # Relative path from 05_place_images/ to 04_frames/kept/
    image_prefix = "../04_frames/kept/"

    if out_final.exists() and not force:
        print(f"Final essay exists, skipping ({out_final})")
        return True
    if not essay_path.exists():
        print(f"ERROR: {essay_path} not found — run essay step first")
        return False
    if not kept_dir.exists():
        print(f"ERROR: {kept_dir} not found — run extract-frames step first")
        return False

    try:
        essay_text = essay_path.read_text()
        kept = load_kept_frames(classifications_path, kept_dir)

        if not kept:
            print("WARNING: No kept frames found. Copying essay as final.")
            out_placed.write_text(essay_text)
            out_final.write_text(essay_text)
            return True

        # Place images
        with_images = place_images_in_essay(essay_text, kept, image_prefix)
        out_placed.write_text(with_images)
        print(f"Essay with images -> {out_placed}")

        # Annotate figures
        annotated = annotate_essay(with_images)
        if embed:
            annotated = embed_images(annotated, kept_dir, image_prefix)
            print("Embedded images as base64 data URIs")
        out_final.write_text(annotated)
        print(f"Final essay -> {out_final}")
        return True
    except Exception as e:
        print(f"ERROR in place-images step: {e}")
        return False


def _step_score(
    video_id: str, run_dir: Path, model: str, score_dir: Path | None = None,
) -> bool:
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    essay_dir = _step_dir(run_dir, "essay")

    transcript_path = filter_dir / "transcript_clean.txt"
    essay_path = essay_dir / "essay.md"

    if not transcript_path.exists():
        print(f"ERROR: no transcript found in {filter_dir}")
        return False
    if not essay_path.exists():
        print(f"ERROR: {essay_path} not found — run essay step first")
        return False

    try:
        result = score_essay(
            transcript=transcript_path.read_text(),
            essay=essay_path.read_text(),
            model=model,
        )
        _print_score_summary(result)
        if score_dir:
            _write_score_results(result, score_dir)
        return True
    except Exception as e:
        print(f"ERROR in score step: {e}")
        return False


def _write_score_results(result: dict, score_dir: Path) -> None:
    """Write each dimension result as a separate JSON file."""
    score_dir.mkdir(parents=True, exist_ok=True)
    for name, data in result["dimensions"].items():
        output = {k: v for k, v in data.items() if k != "reasoning"}
        path = score_dir / f"{name}.json"
        path.write_text(json.dumps(output, indent=2))
    print(f"Dimension results written to {score_dir}")


def _print_score_summary(result: dict) -> None:
    """Print a formatted score summary table to the terminal."""
    dims = result["dimensions"]
    print(f"\n{'─' * 40}")
    print(f"  {'Dimension':<20} {'Score':>5}")
    print(f"{'─' * 40}")
    for name, data in dims.items():
        print(f"  {name:<20} {data['score']:>5}/10")
    print(f"{'─' * 40}")
    print(f"  {'OVERALL':<20} {result['overall_score']:>5}/10")
    print(f"{'─' * 40}")
    print(f"\n  Model: {result['model']}")
    if "summary" in result:
        print(f"\n  {result['summary']}")
    print()


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

@app.command()
def run(
    url: str = typer.Argument(..., help="YouTube video URL"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Re-run all steps even if outputs exist"),
    embed: bool = typer.Option(True, "--embed/--no-embed", help="Embed images as base64 data URIs"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Run the full pipeline: download -> transcript -> filter sponsors -> essay -> frames -> place images."""
    video_id = extract_video_id(url)
    run_dir = _run_dir(video_id, output_dir)
    metadata = _save_metadata(run_dir, url, video_id, cookies)
    print(f"Video ID: {video_id}")
    print(f"Run dir:  {run_dir}\n")

    print("=" * 60)
    print("Step 0/6: Download video + metadata")
    print("=" * 60)
    ok = _step_download(video_id, run_dir, cookies, force)
    if not ok:
        print("\nPipeline stopped at download step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 1/6: Transcript (Deepgram)")
    print("=" * 60)
    ok = _step_transcript(run_dir, force, metadata)
    if not ok:
        print("\nPipeline stopped at transcript step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 2/6: Filter sponsors")
    print("=" * 60)
    ok = _step_filter_sponsors(video_id, run_dir, force)
    if not ok:
        print("\nPipeline stopped at filter-sponsors step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 3/6: Essay")
    print("=" * 60)
    ok = _step_essay(video_id, run_dir, force)
    if not ok:
        print("\nPipeline stopped at essay step.")
        raise typer.Exit(1)

    # Sub-step: generate Key Takeaways
    essay_path = _step_dir(run_dir, "essay") / "essay.md"
    summarize_essay(essay_path, force=force)

    print(f"\n{'=' * 60}")
    print("Step 4/6: Extract frames")
    print("=" * 60)
    ok = _step_extract_frames(video_id, run_dir, force)
    if not ok:
        print("\nPipeline stopped at extract-frames step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Step 5-6/6: Place images + annotate")
    print("=" * 60)
    ok = _step_place_images(video_id, run_dir, embed, force)
    if not ok:
        print("\nPipeline stopped at place-images step.")
        raise typer.Exit(1)

    print(f"\n{'=' * 60}")
    print("Done!")
    print("=" * 60)
    final = run_dir / STEP_DIRS["place_images"] / "essay_final.md"
    print(f"Final essay: {final}")


@app.command()
def transcript(
    url: str = typer.Argument(..., help="YouTube video URL"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing transcript"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Download video and extract transcript via Deepgram."""
    video_id = extract_video_id(url)
    run_dir = _run_dir(video_id, output_dir)
    metadata = _save_metadata(run_dir, url, video_id, cookies)
    print(f"Video ID: {video_id}")

    if not _step_download(video_id, run_dir, cookies, force):
        raise typer.Exit(1)
    if not _step_transcript(run_dir, force, metadata):
        raise typer.Exit(1)


@app.command()
def diarize(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Re-run diarization"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Download video (if needed) and run Deepgram diarization."""
    run_dir = _run_dir(video_id, output_dir)
    dl_dir = _step_dir(run_dir, "download")
    transcript_dir = _step_dir(run_dir, "transcript")

    # Load or create metadata
    meta_path = dl_dir / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
    else:
        url = f"https://www.youtube.com/watch?v={video_id}"
        metadata = _save_metadata(run_dir, url, video_id, cookies)

    if not _step_download(video_id, run_dir, cookies, force=False):
        raise typer.Exit(1)

    # Find video in download dir
    video_files = sorted(dl_dir.glob("video.*"))
    if not video_files:
        print(f"ERROR: No video file in {dl_dir}")
        raise typer.Exit(1)

    try:
        transcribe_with_deepgram(video_files[0], transcript_dir, metadata, force)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        raise typer.Exit(1)


@app.command("filter-sponsors")
def filter_sponsors_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    force: bool = typer.Option(False, "--force", help="Re-run sponsor filtering"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Filter sponsor/ad segments from existing transcript."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_filter_sponsors(video_id, run_dir, force):
        raise typer.Exit(1)


@app.command()
def essay(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing essay"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Generate essay from existing transcript."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_essay(video_id, run_dir, force):
        raise typer.Exit(1)
    essay_path = _step_dir(run_dir, "essay") / "essay.md"
    summarize_essay(essay_path, force=force)


@app.command()
def download(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    cookies: str | None = typer.Option(None, "--cookies", help="Path to cookies.txt"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing video"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Download video only."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_download(video_id, run_dir, cookies, force):
        raise typer.Exit(1)


@app.command("extract-frames")
def extract_frames_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    force: bool = typer.Option(False, "--force", help="Re-extract frames"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Extract and classify frames from existing video."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_extract_frames(video_id, run_dir, force):
        raise typer.Exit(1)


@app.command("place-images")
def place_images_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    embed: bool = typer.Option(True, "--embed/--no-embed", help="Embed images as base64 data URIs"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
) -> None:
    """Place images and annotate figures in existing essay."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_place_images(video_id, run_dir, embed, force):
        raise typer.Exit(1)


@app.command()
def score(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    model: str = typer.Option("claude-sonnet-4-5-20250929", "--model", "-m", help="Model to use for judging"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
    score_dir: Path | None = typer.Option(None, "--score-dir", "-s", help="Directory to write per-dimension JSON results"),
) -> None:
    """Score essay quality against the source transcript."""
    run_dir = _run_dir(video_id, output_dir)
    if not _step_score(video_id, run_dir, model, score_dir):
        raise typer.Exit(1)


@app.command("score-dimension")
def score_dimension_cmd(
    video_id: str = typer.Argument(..., help="YouTube video ID (run dir must exist)"),
    dimension: str = typer.Argument(..., help="Dimension to score (faithfulness, proportionality, embellishment, hallucination, tone)"),
    model: str = typer.Option("claude-sonnet-4-5-20250929", "--model", "-m", help="Model to use for judging"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o", help="Base output directory (default: runs/)"),
    score_dir: Path | None = typer.Option(None, "--score-dir", "-s", help="Directory to write dimension JSON result"),
) -> None:
    """Score the essay on a single quality dimension."""
    if dimension not in DIMENSION_NAMES:
        print(f"ERROR: unknown dimension '{dimension}'. Choose from: {', '.join(DIMENSION_NAMES)}")
        raise typer.Exit(1)

    run_dir = _run_dir(video_id, output_dir)
    filter_dir = _step_dir(run_dir, "filter_sponsors")
    essay_dir = _step_dir(run_dir, "essay")

    transcript_path = filter_dir / "transcript_clean.txt"
    essay_path = essay_dir / "essay.md"

    if not transcript_path.exists():
        print(f"ERROR: no transcript found in {filter_dir}")
        raise typer.Exit(1)
    if not essay_path.exists():
        print(f"ERROR: {essay_path} not found — run essay step first")
        raise typer.Exit(1)

    dim_result = score_one(transcript_path.read_text(), essay_path.read_text(), dimension, model)
    print(f"\n  {dimension}: {dim_result['score']}/10")
    print(f"  {dim_result['rationale']}\n")

    if score_dir:
        score_dir.mkdir(parents=True, exist_ok=True)
        output = {k: v for k, v in dim_result.items() if k != "reasoning"}
        path = score_dir / f"{dimension}.json"
        path.write_text(json.dumps(output, indent=2))
        print(f"Result written to {path}")


@app.command()
def serve(
    no_workers: bool = typer.Option(False, "--no-workers", help="Disable background workers"),
) -> None:
    """Start background workers (web server runs separately via Next.js)."""
    import time

    from . import db

    db.init_db()

    if no_workers:
        print("Workers disabled. Nothing to do.")
        return

    from .worker import start_worker_threads

    print("Starting background workers...")
    start_worker_threads()
    print("Workers running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping workers.")


WORKER_NAMES = ["discover", "download", "process", "deliver"]


@app.command()
def worker(
    name: str = typer.Argument(..., help=f"Worker to run: {', '.join(WORKER_NAMES)}"),
    interval: float = typer.Option(0, "--interval", help="Poll interval in seconds (0 = use default)"),
) -> None:
    """Run a single worker process (for production deployment)."""
    if name not in WORKER_NAMES:
        print(f"Unknown worker: {name}. Choose from: {', '.join(WORKER_NAMES)}")
        raise typer.Exit(1)

    from . import db

    db.init_db()

    from .discover_worker import discover_loop
    from .download_worker import download_loop
    from .process_worker import process_loop
    from .deliver_worker import deliver_loop

    loops: dict[str, tuple[callable, float]] = {
        "discover": (discover_loop, 60.0),
        "download": (download_loop, 10.0),
        "process": (process_loop, 10.0),
        "deliver": (deliver_loop, 15.0),
    }

    loop_fn, default_interval = loops[name]
    actual_interval = interval if interval > 0 else default_interval
    loop_fn(actual_interval)


if __name__ == "__main__":
    app()
