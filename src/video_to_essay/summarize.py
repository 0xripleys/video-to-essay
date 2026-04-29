"""Generate a Key Takeaways section and prepend it to an essay."""

import json
import logging
import re
from pathlib import Path

from video_to_essay import llm

logger = logging.getLogger(__name__)


def summarize_essay(
    essay_path: Path,
    force: bool = False,
    model: str | None = None,
) -> None:
    """Read an essay, generate 3-5 key takeaway bullets, and prepend them after the H1 title.

    Skips if the essay already contains a ## Key Takeaways section (unless force=True).
    Overwrites the essay file in place.
    """
    text = essay_path.read_text()

    if re.search(r"^#{1,3}\s+Key Takeaways", text, re.MULTILINE) and not force:
        logger.info("Key Takeaways already present, skipping (%s)", essay_path)
        return

    text = _strip_takeaways(text)

    logger.info("Generating Key Takeaways...")

    tool = {
        "type": "function",
        "function": {
            "name": "key_takeaways",
            "description": "Return 3-5 key takeaways from the essay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "takeaways": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5,
                        "description": (
                            "Each takeaway is one concise sentence capturing a main "
                            "argument, finding, or insight. Be specific and concrete. "
                            "Do NOT start with 'The video...' or 'The author...'."
                        ),
                    },
                },
                "required": ["takeaways"],
            },
        },
    }

    with llm.run_context(essay_path.parent):
        response = llm.complete(
            task="summarize",
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract key takeaways from essays. "
                        "Use the key_takeaways tool to return them."
                    ),
                },
                {"role": "user", "content": text},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "key_takeaways"}},
            max_tokens=1024,
        )

    tool_call = response.choices[0].message.tool_calls[0]
    tool_input = json.loads(tool_call.function.arguments)
    takeaways = tool_input["takeaways"][:5]
    bullets = "\n\n".join(f"- {t}" for t in takeaways)

    h1_match = re.match(r"(# .+\n)", text)
    if h1_match:
        insert_pos = h1_match.end()
        updated = (
            text[:insert_pos]
            + f"\n## Key Takeaways\n\n{bullets}\n\n---\n\n## Transcript\n\n"
            + text[insert_pos:]
        )
    else:
        updated = f"## Key Takeaways\n\n{bullets}\n\n---\n\n## Transcript\n\n" + text

    essay_path.write_text(updated)
    logger.info("Key Takeaways added -> %s", essay_path)


def _strip_takeaways(text: str) -> str:
    """Remove all existing Key Takeaways sections (and associated --- / ## Transcript) from the essay."""
    return re.sub(
        r"\n*#{1,3}\s+Key Takeaways\n+(?:[•\-\*] .+\n*)+(?:---\n+)?(?:## Transcript\n+)?",
        "\n",
        text,
    )
