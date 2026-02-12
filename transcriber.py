"""
YouTube Video to Essay Tool

Extracts a transcript from a YouTube video and converts it to a well-structured essay
using Claude API.

Usage:
    python transcriber.py <youtube_url> [--cookies <cookies.txt>] [--output <output.md>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def fetch_transcript_ytdlp(video_id: str, cookies_path: str | None = None) -> str:
    """Fetch transcript using yt-dlp in JSON3 format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "subs")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--remote-components", "ejs:github",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "en.*",
            "--sub-format", "json3",
            "--skip-download",
            "-o", output_path,
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Find the downloaded JSON3 file
        json3_files = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.endswith(".json3")
        ]

        if not json3_files:
            raise RuntimeError(
                f"yt-dlp failed to download subtitles.\n"
                f"stderr: {result.stderr}\n"
                f"stdout: {result.stdout}"
            )

        return parse_json3(json3_files[0])


def fetch_transcript_api(video_id: str) -> str:
    """Fetch transcript using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi

    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id, languages=["en"])

    lines = []
    for snippet in transcript:
        minutes = int(snippet.start // 60)
        seconds = int(snippet.start % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {snippet.text}")

    return "\n".join(lines)


def parse_json3(filepath: str) -> str:
    """Parse a YouTube JSON3 subtitle file into clean timestamped text.

    Filters out 'aAppend' events (rolling subtitle duplicates) to get
    clean, non-duplicated transcript text. Groups into ~30s paragraphs.
    """
    with open(filepath) as f:
        data = json.load(f)

    events = data.get("events", [])

    # Extract only non-append events with actual text
    segments = []
    for e in events:
        if e.get("aAppend"):
            continue
        segs = e.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        start_ms = e.get("tStartMs", 0)
        segments.append((start_ms, text))

    # Group into ~30s paragraphs
    paragraphs = []
    current_para = []
    para_start = 0

    for start_ms, text in segments:
        if not current_para:
            para_start = start_ms
        current_para.append(text)

        if start_ms - para_start >= 30000:
            total_sec = para_start // 1000
            minutes = total_sec // 60
            seconds = total_sec % 60
            paragraphs.append(f"[{minutes:02d}:{seconds:02d}] {' '.join(current_para)}")
            current_para = []

    if current_para:
        total_sec = para_start // 1000
        minutes = total_sec // 60
        seconds = total_sec % 60
        paragraphs.append(f"[{minutes:02d}:{seconds:02d}] {' '.join(current_para)}")

    return "\n\n".join(paragraphs)


def transcript_to_essay(transcript: str, api_key: str | None = None) -> str:
    """Convert a transcript to an essay using Claude API.

    Uses Strategy 1 (Simple Direct) which scored highest on coverage (8.5/10).
    """
    import anthropic

    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "Convert this YouTube video transcript into a well-written essay.\n\n"
                f"{transcript}"
            ),
        }],
    )

    return msg.content[0].text


def fetch_transcript(video_id: str, cookies_path: str | None = None) -> str:
    """Fetch transcript, trying youtube-transcript-api first, then yt-dlp."""
    # Try youtube-transcript-api first (lighter, no video download)
    try:
        print("Trying youtube-transcript-api...")
        return fetch_transcript_api(video_id)
    except Exception as e:
        print(f"youtube-transcript-api failed: {e}")

    # Fall back to yt-dlp
    print("Trying yt-dlp...")
    return fetch_transcript_ytdlp(video_id, cookies_path)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a YouTube video into a well-written essay."
    )
    parser.add_argument("url", help="YouTube video URL or video ID")
    parser.add_argument("--cookies", help="Path to cookies.txt for YouTube auth")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument(
        "--transcript-only",
        action="store_true",
        help="Only extract and print the transcript, don't generate essay",
    )
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    print(f"Video ID: {video_id}")

    # Step 1: Extract transcript
    transcript = fetch_transcript(video_id, args.cookies)
    print(f"Transcript: {len(transcript)} characters")

    if args.transcript_only:
        if args.output:
            with open(args.output, "w") as f:
                f.write(transcript)
            print(f"Transcript saved to {args.output}")
        else:
            print(transcript)
        return

    # Step 2: Generate essay
    print("Generating essay...")
    essay = transcript_to_essay(transcript, args.api_key)
    print(f"Essay: {len(essay)} characters")

    if args.output:
        with open(args.output, "w") as f:
            f.write(essay)
        print(f"Essay saved to {args.output}")
    else:
        print("\n" + "=" * 80)
        print(essay)


if __name__ == "__main__":
    main()
