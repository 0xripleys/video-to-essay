"""
Place extracted video frames into essays and annotate with figure references.

Commands:
  place    — Insert images into an existing essay via LLM (step 3)
  annotate — Number images as figures with captions, add figure references into prose (step 4)
"""

import base64
import json
import re
from pathlib import Path

import anthropic
import typer

app = typer.Typer(help="Place extracted video frames into essays and annotate with figures.")


def load_kept_frames(frames_dir: Path) -> list[dict[str, str | int]]:
    """Load classifications.json and filter to only frames present in kept/."""
    classifications_path = frames_dir / "classifications.json"
    if not classifications_path.exists():
        typer.echo(f"Error: {classifications_path} not found", err=True)
        raise typer.Exit(1)

    all_classifications: list[dict[str, str | int]] = json.loads(
        classifications_path.read_text()
    )

    kept_dir = frames_dir / "kept"
    kept_names = {p.name for p in kept_dir.glob("frame_*.jpg")} if kept_dir.exists() else set()

    kept = [c for c in all_classifications if c.get("frame") in kept_names]
    kept.sort(key=lambda c: c.get("timestamp", ""))
    return kept


def format_frame_list(frames: list[dict[str, str | int]]) -> str:
    """Format kept frames into a text list for LLM prompts."""
    lines: list[str] = []
    for f in frames:
        lines.append(
            f"- images/{f['frame']} [{f['timestamp']}] - {f.get('description', '')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: Place images into essay
# ---------------------------------------------------------------------------

@app.command()
def place(
    essay: Path = typer.Option(..., "--essay", "-e", help="Pre-generated essay markdown file"),
    frames_dir: Path = typer.Option(Path("frames"), "--frames-dir", "-f", help="Directory with classifications.json and kept/"),
    output: Path = typer.Option(Path("essay_with_images.md"), "--output", "-o", help="Output markdown file"),
    embed: bool = typer.Option(False, "--embed", help="Embed images as base64 data URIs"),
) -> None:
    """Step 3: Insert images into an existing essay via LLM."""
    essay_text = essay.read_text()
    kept = load_kept_frames(frames_dir)

    if not kept:
        typer.echo("No kept frames found. Aborting.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Inserting {len(kept)} images into existing essay...")

    frame_list = format_frame_list(kept)

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": (
                    "Here is a markdown essay and a set of images extracted from the source video. "
                    "Insert each image at the most appropriate position in the essay. Place each "
                    "image on its own line between paragraphs where it is most relevant. "
                    "Use markdown image syntax: ![description](path)\n\n"
                    "Use every image exactly once. Do not modify the essay text — only add image "
                    "lines. Return the full essay with images inserted.\n\n"
                    f"Available images:\n{frame_list}\n\n"
                    f"Essay:\n{essay_text}"
                ),
            }
        ],
    )

    result = msg.content[0].text
    _print_image_stats(result, kept)
    if embed:
        result = embed_images(result, frames_dir)
        typer.echo("Embedded images as base64 data URIs")
    output.write_text(result)
    typer.echo(f"Wrote {len(result)} chars to {output}")


# ---------------------------------------------------------------------------
# Step 4: Annotate — add figure numbers, captions, and prose references
# ---------------------------------------------------------------------------

def _number_figures(essay: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Replace ![alt](src) with numbered figures. Returns (new_essay, figure_list).

    Each figure becomes:
        ![alt](src)
        **Figure N:** alt text

    Returns the figure list as [(number, alt, src), ...] for the LLM prompt.
    """
    figures: list[tuple[int, str, str]] = []
    counter = 0

    def replace_match(m: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        alt = m.group(1)
        src = m.group(2)
        figures.append((counter, alt, src))
        return f"![{alt}]({src})\n*Figure {counter}: {alt}*"

    result = re.sub(r"!\[(.*?)\]\(([^)]+)\)", replace_match, essay)
    return result, figures


@app.command()
def annotate(
    essay: Path = typer.Option(..., "--essay", "-e", help="Essay markdown with images already placed"),
    output: Path = typer.Option(Path("essay_annotated.md"), "--output", "-o", help="Output markdown file"),
    frames_dir: Path = typer.Option(Path("frames"), "--frames-dir", "-f", help="Directory with kept/ (for --embed)"),
    embed: bool = typer.Option(False, "--embed", help="Embed images as base64 data URIs"),
) -> None:
    """Step 4: Add figure numbers, captions, and weave figure references into prose."""
    essay_text = essay.read_text()

    # Step 4a: Mechanically number figures and add captions
    numbered_essay, figures = _number_figures(essay_text)

    if not figures:
        typer.echo("No images found in essay. Nothing to annotate.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Numbered {len(figures)} figures. Adding references via LLM...")

    # Build a figure summary for the prompt
    figure_summary = "\n".join(
        f"- Figure {num}: {alt}" for num, alt, _src in figures
    )

    # Step 4b: LLM pass to insert natural figure references into prose
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": (
                    "Below is a markdown essay with numbered figures (images with captions like "
                    "**Figure N:** description). Your task is to add natural references to these "
                    "figures in the essay prose.\n\n"
                    "Rules:\n"
                    "- Add references like '(see Figure 1)', 'as shown in Figure 3', "
                    "'Figure 2 illustrates', etc. in the most relevant nearby paragraph\n"
                    "- Every figure must be referenced at least once in the prose\n"
                    "- Do NOT move, remove, or modify the image lines or figure captions\n"
                    "- Do NOT rewrite the prose — only insert short figure references into "
                    "existing sentences\n"
                    "- Return the complete essay\n\n"
                    f"Figures in this essay:\n{figure_summary}\n\n"
                    f"Essay:\n{numbered_essay}"
                ),
            }
        ],
    )

    result = msg.content[0].text
    if embed:
        result = embed_images(result, frames_dir)
        typer.echo("Embedded images as base64 data URIs")
    output.write_text(result)
    typer.echo(f"Wrote {len(result)} chars to {output}")

    # Count figure references in prose
    for num, alt, _src in figures:
        ref_count = len(re.findall(rf"Figure\s+{num}\b", result)) - 1  # subtract the caption itself
        status = "ok" if ref_count > 0 else "MISSING"
        typer.echo(f"  Figure {num}: {ref_count} reference(s) [{status}] — {alt[:60]}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def embed_images(essay: str, frames_dir: Path) -> str:
    """Replace image file paths with base64 data URIs for self-contained markdown."""
    kept_dir = frames_dir / "kept"

    def replace_match(m: re.Match[str]) -> str:
        alt = m.group(1)
        path = m.group(2)
        filename = Path(path).name
        img_path = kept_dir / filename
        if not img_path.exists():
            return m.group(0)
        b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
        return f"![{alt}](data:image/jpeg;base64,{b64})"

    return re.sub(r"!\[(.*?)\]\((images/frame_\d+\.jpg)\)", replace_match, essay)


def _print_image_stats(essay: str, kept: list[dict[str, str | int]]) -> None:
    """Print how many images were placed vs available."""
    placed_files = re.findall(r"!\[.*?\]\(images/(frame_\d+\.jpg)\)", essay)
    data_uri_count = len(re.findall(r"!\[.*?\]\(data:image/jpeg;base64,", essay))
    placed_names = set(placed_files)
    kept_names = {str(f["frame"]) for f in kept}

    total_placed = len(placed_names) or data_uri_count
    typer.echo(f"\nImage placement stats:")
    typer.echo(f"  Available: {len(kept_names)}")
    typer.echo(f"  Placed:    {total_placed}")
    if placed_names:
        missing = kept_names - placed_names
        if missing:
            typer.echo(f"  Missing:   {', '.join(sorted(missing))}")
        extra = placed_names - kept_names
        if extra:
            typer.echo(f"  Extra:     {', '.join(sorted(extra))}")


if __name__ == "__main__":
    app()
