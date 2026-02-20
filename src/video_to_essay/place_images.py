"""
Place extracted video frames into essays and annotate with figure references.

Used as a library by main.py. Not intended to be run directly.
"""

import base64
import json
import re
import time
from pathlib import Path

import anthropic


def _stream_message(client: anthropic.Anthropic, **kwargs: object) -> str:
    """Create a message with streaming to handle long requests.

    Includes exponential backoff retry for rate limit errors.
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            chunks: list[str] = []
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
            return "".join(chunks)
        except anthropic.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt * 15  # 15, 30, 60, 120s
            print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait)
    return ""  # unreachable


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

    Uses a JSON placement plan approach: the LLM returns a small JSON mapping
    each image to a paragraph index, then insertion is done mechanically.
    This avoids output token limits for long essays.
    """
    if not kept_frames:
        raise ValueError("No kept frames to place")

    print(f"Inserting {len(kept_frames)} images into essay...")

    frame_list = format_frame_list(kept_frames, image_prefix)

    # Number paragraphs so the LLM can reference them
    paragraphs = essay_text.split("\n\n")
    numbered = "\n\n".join(f"[P{i}] {p}" for i, p in enumerate(paragraphs))

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    "Here is a markdown essay with numbered paragraphs [P0], [P1], etc., "
                    "and a set of images extracted from the source video.\n\n"
                    "For each image, decide which paragraph it should be placed AFTER. "
                    "Return ONLY a JSON array of placements, one per image, in this format:\n"
                    '[{"image": "images/frame_0042.jpg", "after": 5, "alt": "short description"}]\n\n'
                    "Rules:\n"
                    "- Place each image after the paragraph where it is most contextually relevant\n"
                    "- Use every image exactly once\n"
                    "- The alt text should be a brief description of what the image shows\n"
                    "- Return ONLY valid JSON, no other text\n\n"
                    f"Available images:\n{frame_list}\n\n"
                    f"Essay:\n{numbered}"
                ),
            }
        ],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    placements: list[dict] = json.loads(raw)

    # Group placements by paragraph index
    insert_after: dict[int, list[str]] = {}
    for p in placements:
        idx = int(p["after"])
        alt = p.get("alt", "")
        img = p["image"]
        insert_after.setdefault(idx, []).append(f"![{alt}]({img})")

    # Build result by inserting image lines after designated paragraphs
    result_parts: list[str] = []
    for i, para in enumerate(paragraphs):
        result_parts.append(para)
        if i in insert_after:
            for img_line in insert_after[i]:
                result_parts.append(img_line)

    result = "\n\n".join(result_parts)
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

    Uses a JSON approach: the LLM returns figure reference insertions as a list
    of {figure, text_to_find, replacement} objects, then we apply them mechanically.
    """
    # Step 1: Mechanically number figures and add captions
    numbered_essay, figures = _number_figures(essay_text)

    if not figures:
        raise ValueError("No images found in essay. Nothing to annotate.")

    print(f"Numbered {len(figures)} figures. Adding references via LLM in batches of {batch_size}...")

    # Step 2: LLM returns insertion instructions as JSON
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
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Below is a markdown essay with numbered figures. Add natural references "
                        "to ONLY the listed figures by finding a relevant sentence near each figure "
                        "and inserting a short reference.\n\n"
                        "Return ONLY a JSON array where each entry specifies a text replacement:\n"
                        '[{"figure": 1, "find": "exact sentence or phrase from the essay", '
                        '"replace": "same text with figure reference naturally inserted"}]\n\n'
                        "Rules:\n"
                        '- References should read naturally: "(see Figure 1)", "as shown in Figure 3", etc.\n'
                        "- The 'find' field must be an EXACT substring from the essay (10-80 chars)\n"
                        "- The 'replace' field should be the same text with only a figure reference added\n"
                        "- Every listed figure must have at least one reference\n"
                        "- Return ONLY valid JSON\n\n"
                        f"Figures to reference:\n{figure_summary}\n\n"
                        f"Essay:\n{result}"
                    ),
                }
            ],
        )

        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            replacements: list[dict] = json.loads(raw)
            for r in replacements:
                find_text = r.get("find", "")
                replace_text = r.get("replace", "")
                if find_text and replace_text and find_text in result:
                    result = result.replace(find_text, replace_text, 1)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  WARNING: Could not parse annotation batch: {e}")

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
