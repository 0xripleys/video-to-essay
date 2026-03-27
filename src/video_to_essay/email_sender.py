"""Send completed essays via AgentMail."""

import os

import markdown
from agentmail import AgentMail


def _get_client() -> AgentMail:
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    if not api_key:
        raise RuntimeError("AGENTMAIL_API_KEY environment variable is required")
    return AgentMail(api_key=api_key)


def _essay_to_html(essay_md: str) -> str:
    """Convert markdown essay to HTML email body.

    Handles base64-embedded images by passing them through as raw HTML.
    """
    html_body = markdown.markdown(essay_md, extensions=["extra", "smarty"])
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 700px; margin: 0 auto; padding: 20px; line-height: 1.7; color: #333; }}
  h1 {{ font-size: 1.8em; margin-bottom: 0.3em; }}
  h2 {{ font-size: 1.4em; margin-top: 1.5em; }}
  img {{ max-width: 100%; height: auto; border-radius: 4px; margin: 1em 0; }}
  em {{ color: #666; }}
  blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""


def send_essay(
    to_email: str,
    video_title: str,
    essay_md: str,
    inbox_id: str | None = None,
) -> None:
    """Send the completed essay to the user's email."""
    client = _get_client()
    inbox = inbox_id or os.environ.get("AGENTMAIL_INBOX_ID")
    if not inbox:
        raise RuntimeError("AGENTMAIL_INBOX_ID environment variable is required")

    html = _essay_to_html(essay_md)

    # Send with essay markdown as attachment
    client.inboxes.messages.send(
        inbox,
        to=to_email,
        subject=f'Your essay is ready: "{video_title}"',
        html=html,
        text=essay_md,
    )
    print(f"Essay emailed to {to_email}")
