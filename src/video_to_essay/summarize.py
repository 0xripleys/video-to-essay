"""Generate a Key Takeaways section and prepend it to an essay."""

import json
import re
from pathlib import Path


def summarize_essay(essay_path: Path, force: bool = False) -> None:
    """Read an essay, generate 3-5 key takeaway bullets, and prepend them after the H1 title.

    Skips if the essay already contains a ## Key Takeaways section (unless force=True).
    Overwrites the essay file in place.
    """
    import anthropic

    text = essay_path.read_text()

    if re.search(r"^#{1,3}\s+Key Takeaways", text, re.MULTILINE) and not force:
        print(f"Key Takeaways already present, skipping ({essay_path})")
        return

    # Strip any existing Key Takeaways sections if forcing
    text = _strip_takeaways(text)

    print("Generating Key Takeaways...")
    client = anthropic.Anthropic()

    tool = {
        "name": "key_takeaways",
        "description": "Return 3-5 key takeaways from the essay.",
        "input_schema": {
            "type": "object",
            "properties": {
                "takeaways": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 5,
                    "description": "Each takeaway is one concise sentence capturing a main argument, finding, or insight. Be specific and concrete. Do NOT start with 'The video...' or 'The author...'.",
                },
            },
            "required": ["takeaways"],
        },
    }

    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=(
            "You extract key takeaways from essays. Use the key_takeaways tool to return them."
        ),
        messages=[{
            "role": "user",
            "content": text,
        }],
        tools=[tool],
        tool_choice={"type": "tool", "name": "key_takeaways"},
    )

    tool_input = next(b for b in msg.content if b.type == "tool_use").input
    takeaways = tool_input["takeaways"][:5]
    bullets = "\n\n".join(f"- {t}" for t in takeaways)

    # Insert after the H1 title
    h1_match = re.match(r"(# .+\n)", text)
    if h1_match:
        insert_pos = h1_match.end()
        updated = text[:insert_pos] + f"\n## Key Takeaways\n\n{bullets}\n\n---\n\n## Transcript\n\n" + text[insert_pos:]
    else:
        # No H1 found — prepend at the top
        updated = f"## Key Takeaways\n\n{bullets}\n\n---\n\n## Transcript\n\n" + text

    essay_path.write_text(updated)
    print(f"Key Takeaways added -> {essay_path}")


def _strip_takeaways(text: str) -> str:
    """Remove all existing Key Takeaways sections (and associated --- / ## Transcript) from the essay."""
    # Match Key Takeaways heading + bullets (with optional blank lines between them)
    # + optional hr + optional Transcript heading
    return re.sub(
        r"\n*#{1,3}\s+Key Takeaways\n+(?:[•\-\*] .+\n*)+(?:---\n+)?(?:## Transcript\n+)?",
        "\n",
        text,
    )
