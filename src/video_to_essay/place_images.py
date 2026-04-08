"""
Place extracted video frames into essays and annotate with figure references.

Used as a library by main.py. Not intended to be run directly.
"""

import base64
import io
import json
import re
from pathlib import Path

from PIL import Image

from . import llm_client


def load_kept_frames(
    classifications_path: Path, kept_dir: Path
) -> list[dict[str, str | int]]:
    """Load classifications.json and filter to only frames present in kept_dir."""
    if not classifications_path.exists():
        raise FileNotFoundError(f"{classifications_path} not found")

    all_classifications: list[dict[str, str | int]] = json.loads(
        classifications_path.read_text()
    )

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

    placement_schema = {
        "type": "object",
        "properties": {
            "placements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "image": {
                            "type": "string",
                            "description": "Image filename",
                        },
                        "after": {
                            "type": "integer",
                            "description": "Paragraph index to place image after",
                        },
                        "alt": {
                            "type": "string",
                            "description": "Short description of what the image shows",
                        },
                    },
                    "required": ["image", "after", "alt"],
                },
            }
        },
        "required": ["placements"],
    }

    tool_input = llm_client.text_complete_with_tool(
        user=(
            "Here is a markdown essay with numbered paragraphs [P0], [P1], etc., "
            "and a set of images extracted from the source video.\n\n"
            "For each image, decide which paragraph it should be placed AFTER.\n\n"
            "Rules:\n"
            "- Place each image after the paragraph where it is most contextually relevant\n"
            "- Use every image exactly once\n"
            "- The alt text should be a brief description of what the image shows\n\n"
            f"Available images:\n{frame_list}\n\n"
            f"Essay:\n{numbered}"
        ),
        max_tokens=16384,
        model_class="smart",
        tool_name="place_images",
        tool_description="Place images into the essay at appropriate positions.",
        tool_schema=placement_schema,
    )
    placements: list[dict] = tool_input.get("placements", [])

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
    _print_image_stats(result, kept_frames, image_prefix)
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
    result = numbered_essay

    annotation_schema = {
        "type": "object",
        "properties": {
            "replacements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "figure": {"type": "integer"},
                        "find": {"type": "string"},
                        "replace": {"type": "string"},
                    },
                    "required": ["figure", "find", "replace"],
                },
            }
        },
        "required": ["replacements"],
    }

    for i in range(0, len(figures), batch_size):
        batch = figures[i : i + batch_size]
        figure_summary = "\n".join(
            f"- Figure {num}: {alt}" for num, alt, _src in batch
        )
        batch_nums = ", ".join(str(num) for num, _, _ in batch)
        print(f"  Batch: Figure {batch_nums}...")

        try:
            tool_input = llm_client.text_complete_with_tool(
                user=(
                    "Below is a markdown essay with numbered figures. Add natural "
                    "references to ONLY the listed figures by finding a relevant sentence "
                    "near each figure and inserting a short reference.\n\n"
                    "Rules:\n"
                    '- References should read naturally: "(see Figure 1)", "as shown in Figure 3", etc.\n'
                    "- The 'find' field must be an EXACT substring from the essay (10-80 chars)\n"
                    "- The 'replace' field should be the same text with only a figure reference added\n"
                    "- Every listed figure must have at least one reference\n\n"
                    f"Figures to reference:\n{figure_summary}\n\n"
                    f"Essay:\n{result}"
                ),
                max_tokens=4096,
                model_class="smart",
                tool_name="annotate_figures",
                tool_description=(
                    "Return exact-string replacements that add figure references."
                ),
                tool_schema=annotation_schema,
            )
            replacements: list[dict] = tool_input.get("replacements", [])
            for r in replacements:
                find_text = r.get("find", "")
                replace_text = r.get("replace", "")
                if find_text and replace_text and find_text in result:
                    result = result.replace(find_text, replace_text, 1)
        except Exception as e:
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

def _resize_for_email(img_bytes: bytes, max_width: int = 800, quality: int = 70) -> bytes:
    """Resize and compress an image for email embedding."""
    img = Image.open(io.BytesIO(img_bytes))
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def embed_images(
    essay: str, kept_dir: Path, image_prefix: str = "images/"
) -> str:
    """Replace image file paths with base64 data URIs for self-contained markdown."""
    prefix_pattern = re.escape(image_prefix)

    def replace_match(m: re.Match[str]) -> str:
        alt = m.group(1)
        path = m.group(2)
        filename = Path(path).name
        img_path = kept_dir / filename
        if not img_path.exists():
            return m.group(0)
        compressed = _resize_for_email(img_path.read_bytes())
        b64 = base64.b64encode(compressed).decode("utf-8")
        return f"![{alt}](data:image/jpeg;base64,{b64})"

    return re.sub(
        rf"!\[(.*?)\]\(({prefix_pattern}frame_\d+\.jpg)\)", replace_match, essay
    )


def _print_image_stats(
    essay: str, kept: list[dict[str, str | int]], image_prefix: str = "images/"
) -> None:
    """Print how many images were placed vs available."""
    prefix_pattern = re.escape(image_prefix)
    placed_files = re.findall(rf"!\[.*?\]\({prefix_pattern}(frame_\d+\.jpg)\)", essay)
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
