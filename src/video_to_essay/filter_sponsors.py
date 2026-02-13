"""
Sponsor/ad segment detection and removal from transcripts.

Uses Claude Haiku to identify sponsor reads and promotional content,
returning a cleaned transcript and timestamp ranges for downstream filtering.
"""

import json
import re

import anthropic


def filter_sponsors(transcript: str) -> tuple[str, list[tuple[int, int]]]:
    """Identify and remove sponsor segments from a transcript.

    Returns:
        A tuple of (cleaned_transcript, sponsor_ranges) where sponsor_ranges
        is a list of (start_seconds, end_seconds) pairs.
    """
    client = anthropic.Anthropic()

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Analyze this timestamped transcript and identify any sponsor reads, "
                    "advertisements, or promotional segments. These include:\n"
                    "- Direct sponsor mentions (\"this video is brought to you by...\")\n"
                    "- Product promotions and discount codes\n"
                    "- Calls to action for sponsor products/services\n"
                    "- Ad reads embedded within the content\n\n"
                    "Respond with ONLY valid JSON, no other text:\n"
                    "{\n"
                    '  "sponsor_segments": [\n'
                    '    {"start": "MM:SS", "end": "MM:SS", "reason": "brief description"}\n'
                    "  ]\n"
                    "}\n\n"
                    "If there are no sponsor segments, return an empty list.\n"
                    "Use the timestamps from the transcript to mark segment boundaries.\n\n"
                    f"Transcript:\n{transcript}"
                ),
            }
        ],
    )

    raw = msg.content[0].text.strip()
    # Handle markdown code blocks
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(raw)
    segments = parsed.get("sponsor_segments", [])

    sponsor_ranges: list[tuple[int, int]] = []
    for seg in segments:
        start = _parse_mmss(seg["start"])
        end = _parse_mmss(seg["end"])
        if start is not None and end is not None:
            sponsor_ranges.append((start, end))

    cleaned = _strip_segments(transcript, sponsor_ranges)
    return cleaned, sponsor_ranges


def _strip_segments(transcript: str, ranges: list[tuple[int, int]]) -> str:
    """Remove transcript paragraphs whose timestamps fall within sponsor ranges."""
    if not ranges:
        return transcript

    kept_paragraphs: list[str] = []
    for paragraph in transcript.split("\n\n"):
        # Extract timestamp from paragraph start
        match = re.match(r"\[(\d+):(\d{2})\]", paragraph)
        if not match:
            kept_paragraphs.append(paragraph)
            continue
        para_sec = int(match.group(1)) * 60 + int(match.group(2))
        if not any(start <= para_sec <= end for start, end in ranges):
            kept_paragraphs.append(paragraph)

    return "\n\n".join(kept_paragraphs)


def _parse_mmss(timestamp: str) -> int | None:
    """Parse MM:SS timestamp string into total seconds."""
    match = re.match(r"(\d+):(\d{2})", timestamp)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))
