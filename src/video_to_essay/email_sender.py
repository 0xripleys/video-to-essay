"""Send completed essays via AgentMail."""

import logging
import os
import re
import textwrap

import markdown
from agentmail import AgentMail

logger = logging.getLogger(__name__)


def _get_client() -> AgentMail:
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    if not api_key:
        raise RuntimeError("AGENTMAIL_API_KEY environment variable is required")
    return AgentMail(api_key=api_key)


def _insert_scrivi_link(essay_md: str, scrivi_link: str) -> str:
    """Insert the Scrivi link after Key Takeaways bullets, before the ---."""
    if "## Key Takeaways" in essay_md:
        return re.sub(r"(\n---\n)", f"\n{scrivi_link}\n\\1", essay_md, count=1)
    # No Key Takeaways section — insert after H1
    h1_match = re.match(r"(# .+\n)", essay_md)
    if h1_match:
        return essay_md[:h1_match.end()] + f"\n{scrivi_link}\n\n" + essay_md[h1_match.end():]
    return f"{scrivi_link}\n\n" + essay_md


def _essay_to_plaintext(essay_md: str) -> str:
    """Convert markdown essay to plaintext: strip base64 images, wrap lines."""
    plaintext = re.sub(
        r"!\[([^\]]*)\]\(data:image/[^)]+\)",
        r"[Image: \1]",
        essay_md,
    )
    wrapped_lines: list[str] = []
    for line in plaintext.splitlines():
        if not line.strip() or line.startswith("#") or line.startswith(">"):
            wrapped_lines.append(line)
        else:
            wrapped_lines.append(textwrap.fill(line, width=80))
    return "\n".join(wrapped_lines)


def _essay_to_html(essay_md: str) -> str:
    """Convert markdown essay to HTML email body.

    Handles base64-embedded images by passing them through as raw HTML.
    """
    html_body = markdown.markdown(essay_md, extensions=["extra", "smarty"])
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body>
<div style="font-family: -apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; font-size: 16px; line-height: 1.7; color: #333;">
{html_body}
</div>
</body>
</html>"""


def send_essay(
    to_email: str,
    video_title: str,
    essay_md: str,
    inbox_id: str | None = None,
    channel_name: str | None = None,
    video_id: str | None = None,
) -> None:
    """Send the completed essay to the user's email."""
    client = _get_client()
    inbox = inbox_id or os.environ.get("AGENTMAIL_INBOX_ID")
    if not inbox:
        raise RuntimeError("AGENTMAIL_INBOX_ID environment variable is required")

    if video_id:
        scrivi_link = f"[Read on Scrivi](https://scrivi.ink/reader?id={video_id})"
        essay_md = _insert_scrivi_link(essay_md, scrivi_link)

    html = _essay_to_html(essay_md)
    plaintext = _essay_to_plaintext(essay_md)

    client.inboxes.messages.send(
        inbox,
        to=to_email,
        subject=f"{channel_name}: {video_title}" if channel_name else video_title,
        html=html,
        text=plaintext,
    )
    logger.info("Essay emailed to %s", to_email)
