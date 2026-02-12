"""
Place extracted video frames into essays and annotate with figure references.

Used as a library by main.py. Not intended to be run directly.
"""

import base64
import json
import re
from pathlib import Path

import anthropic


def load_kept_frames(frames_dir: Path) -> list[dict[str, str | int]]:
    """Load classifications.json and filter to only frames present in kept/."""
    classifications_path = frames_dir / "classifications.json"
    if not classifications_path.exists():
        raise FileNotFoundError(f"{classifications_path} not found")

    all_classifications: list[dict[str, str | int]] = json.loads(
        classifications_path.read_text()
    )

    kept_dir = frames_dir / "kept"
    kept_names = {p.name for p in kept_dir.glob("frame_*.jpg")} if kept_dir.exists() else set()

    kept = [c for c in all_classifications if c.get("frame") in kept_names]
    kept.sort(key=lambda c: c.get("timestamp", ""))
    return kept


def format_frame_list(
    frames: list[dict[str, str | int]], image_prefix: str = "images/"
) -> str:
    """Format kept frames into a text list for LLM prompts."""
    lines: list[str] = []
    for f in frames:
        lines.append(
            f"- {image_prefix}{f['frame']} [{f['timestamp']}] - {f.get('description', '')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Place images into essay
# ---------------------------------------------------------------------------

def place_images_in_essay(
    essay_text: str,
    kept_frames: list[dict[str, str | int]],
    image_prefix: str = "images/",
) -> str:
    """Insert images into an essay at appropriate positions via LLM.

    Returns the essay text with image markdown lines inserted.
    """
    if not kept_frames:
        raise ValueError("No kept frames to place")

    print(f"Inserting {len(kept_frames)} images into essay...")

    frame_list = format_frame_list(kept_frames, image_prefix)

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
    _print_image_stats(result, kept_frames)
    return result


# ---------------------------------------------------------------------------
# Annotate — add figure numbers, captions, and prose references
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


def annotate_essay(
    essay_text: str,
    batch_size: int = 5,
) -> str:
    """Add figure numbers, captions, and weave figure references into prose.

    Returns the annotated essay text.
    """
    # Step 1: Mechanically number figures and add captions
    numbered_essay, figures = _number_figures(essay_text)

    if not figures:
        raise ValueError("No images found in essay. Nothing to annotate.")

    print(f"Numbered {len(figures)} figures. Adding references via LLM in batches of {batch_size}...")

    # Step 2: LLM passes to insert figure references, batch_size figures at a time
    client = anthropic.Anthropic()
    result = numbered_essay

    for i in range(0, len(figures), batch_size):
        batch = figures[i : i + batch_size]
        figure_summary = "\n".join(
            f"- Figure {num}: {alt}" for num, alt, _src in batch
        )
        batch_nums = ", ".join(str(num) for num, _, _ in batch)
        print(f"  Batch: Figure {batch_nums}...")

        msg = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=16384,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Below is a markdown essay with numbered figures (images with captions like "
                        "*Figure N: description*). Your task is to add natural references to ONLY "
                        "the following figures in the essay prose.\n\n"
                        "Rules:\n"
                        "- Add references like '(see Figure 1)', 'as shown in Figure 3', "
                        "'Figure 2 illustrates', etc. in the most relevant nearby paragraph\n"
                        "- ONLY add references for the figures listed below — do not touch "
                        "any existing figure references already in the text\n"
                        "- Every listed figure must be referenced at least once in the prose\n"
                        "- Do NOT move, remove, or modify the image lines or figure captions\n"
                        "- Do NOT rewrite the prose — only insert short figure references into "
                        "existing sentences\n"
                        "- Return the complete essay\n\n"
                        f"Figures to reference:\n{figure_summary}\n\n"
                        f"Essay:\n{result}"
                    ),
                }
            ],
        )

        result = msg.content[0].text

    # Report figure reference coverage
    for num, alt, _src in figures:
        ref_count = len(re.findall(rf"Figure\s+{num}\b", result)) - 1  # subtract the caption itself
        status = "ok" if ref_count > 0 else "MISSING"
        print(f"  Figure {num}: {ref_count} reference(s) [{status}] — {alt[:60]}")

    return result


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
    print(f"\nImage placement stats:")
    print(f"  Available: {len(kept_names)}")
    print(f"  Placed:    {total_placed}")
    if placed_names:
        missing = kept_names - placed_names
        if missing:
            print(f"  Missing:   {', '.join(sorted(missing))}")
        extra = placed_names - kept_names
        if extra:
            print(f"  Extra:     {', '.join(sorted(extra))}")
