"""
YouTube Video to Essay — transcript extraction, essay generation, and video download.

Used as a library by main.py. Not intended to be run directly.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _stream_message(client: "anthropic.Anthropic", **kwargs: object) -> str:
    """Create a message with streaming to handle long requests."""
    chunks: list[str] = []
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks)


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


def extract_style_profile(transcript: str, api_key: str | None = None) -> str:
    """Analyze transcript to extract a compact style profile.

    Sends the first ~8k chars of the transcript to Haiku and returns a
    ~200-word profile describing formality, phrasing, humor, etc.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    sample = transcript[:8000]

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Analyze the speaking style of this YouTube transcript excerpt. "
                "Return a compact style profile (~200 words) covering:\n"
                "- Formality level (casual/semi-formal/formal)\n"
                "- Characteristic phrases or verbal tics\n"
                "- How the speaker addresses the audience\n"
                "- Sentence patterns (short punchy, long flowing, fragments, etc.)\n"
                "- Humor usage (sarcasm, self-deprecation, deadpan, none, etc.)\n"
                "- Emotional tone (excited, calm, skeptical, enthusiastic, etc.)\n"
                "- 3 short representative quotes that capture the voice\n\n"
                "Be specific and concrete. This profile will be used to preserve "
                "the speaker's voice when converting the transcript to written form.\n\n"
                f"{sample}"
            ),
        }],
    )

    return msg.content[0].text


def _is_multi_speaker(transcript: str) -> bool:
    """Detect if transcript has **Speaker Name** markers from diarization."""
    return bool(re.search(r"^\*\*[^*]+\*\*\s*\[", transcript, re.MULTILINE))


def _extract_speakers(transcript: str) -> list[str]:
    """Extract unique speaker names from attributed transcript."""
    return list(dict.fromkeys(
        re.findall(r"^\*\*([^*]+)\*\*\s*\[", transcript, re.MULTILINE)
    ))


def extract_multi_speaker_style_profile(
    transcript: str, api_key: str | None = None
) -> str:
    """Analyze multi-speaker transcript to extract per-speaker style profiles.

    Sends the first ~8k chars to Haiku and returns a combined multi-speaker
    style analysis covering each speaker's distinct voice.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    speakers = _extract_speakers(transcript)
    sample = transcript[:8000]

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                "Analyze the speaking styles in this multi-speaker transcript excerpt. "
                f"The speakers are: {', '.join(speakers)}.\n\n"
                "For EACH speaker, return a compact style profile (~100 words) covering:\n"
                "- Formality level (casual/semi-formal/formal)\n"
                "- Characteristic phrases or verbal tics\n"
                "- Role in conversation (host, guest, interviewer, etc.)\n"
                "- Sentence patterns (short punchy, long flowing, fragments, etc.)\n"
                "- Humor usage (sarcasm, self-deprecation, deadpan, none, etc.)\n"
                "- Emotional tone (excited, calm, skeptical, enthusiastic, etc.)\n"
                "- 2 short representative quotes that capture their voice\n\n"
                "Be specific and concrete. These profiles will be used to preserve "
                "each speaker's distinct voice when converting the transcript.\n\n"
                f"{sample}"
            ),
        }],
    )

    return msg.content[0].text


def _transcript_to_essay_single(
    transcript: str, client: "anthropic.Anthropic", api_key: str | None
) -> str:
    """Single-speaker essay generation (original path)."""
    print("Extracting style profile from transcript...")
    style_profile = extract_style_profile(transcript, api_key=api_key)
    print("Style profile extracted. Generating essay...")

    system_prompt = f"""\
You are converting a YouTube video transcript into a readable essay. Your #1 job \
is to preserve the speaker's original voice and tone. The essay should read like \
the speaker wrote it themselves, not like an academic rewrote it.

## Speaker's Style Profile
{style_profile}

## KEEP these elements from the original speech:
- Contractions (don't, can't, it's, we're)
- Casual/colloquial words (stuff, thing, kinda, pretty much, a lot, super)
- Hedging language (I think, probably, sort of, maybe, I guess)
- Direct audience address (you, you guys, we)
- Humor, sarcasm, asides, and personality
- Short punchy sentences and fragments when they match the speaker's rhythm
- The speaker's actual word choices — do NOT swap them for fancier synonyms
- First person perspective if the speaker uses it

## NEVER do any of these:
- Replace casual words with formal synonyms (e.g. "use" → "utilize", "big" → "substantial")
- Add academic transition phrases ("Furthermore", "Moreover", "It is worth noting", "In conclusion")
- Remove the speaker's personality, humor, or opinions
- Impose a thesis-introduction-body-conclusion structure
- Add hedging or qualifiers the speaker didn't use
- Make sentences longer or more complex than the original
- Add filler like "This is a testament to" or "It is important to recognize"

## Structure guidance:
- Use section headings that sound like the speaker (casual, not formal)
- Paragraphs should be short — match the speaker's pacing
- Clean up verbal filler (um, uh, like, you know) and repetition
- Fix grammar only where it would be confusing in written form
- Ignore any sponsor reads, advertisements, or promotional content"""

    few_shot_examples = """\
Here are examples of CORRECT vs INCORRECT conversion:

### Example transcript snippet:
"so basically what happened is the company just... they threw a ton of money at the problem and honestly it kinda worked? like nobody expected that"

### CORRECT conversion (preserves voice):
So basically what happened is the company threw a ton of money at the problem, and honestly, it kinda worked. Like, nobody expected that.

### INCORRECT conversion (over-formalized — DO NOT do this):
The company allocated substantial resources to address the challenge, and the strategy proved surprisingly effective. This outcome defied conventional expectations.

---"""

    result = _stream_message(
        client,
        model="claude-sonnet-4-5-20250929",
        max_tokens=16384,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"{few_shot_examples}\n\n"
                "Now convert this transcript into an essay. Preserve the speaker's "
                "voice exactly as described in the style profile above.\n\n"
                f"{transcript}"
            ),
        }],
    )

    return result


def _transcript_to_essay_multi(
    transcript: str, client: "anthropic.Anthropic", api_key: str | None
) -> str:
    """Multi-speaker essay generation (dialogue-style)."""
    speakers = _extract_speakers(transcript)
    print(f"Multi-speaker transcript detected: {', '.join(speakers)}")

    print("Extracting per-speaker style profiles...")
    style_profile = extract_multi_speaker_style_profile(transcript, api_key=api_key)
    print("Style profiles extracted. Generating dialogue essay...")

    speaker_list = "\n".join(f"- {s}" for s in speakers)

    system_prompt = f"""\
You are converting a multi-speaker YouTube transcript (podcast, interview, panel) \
into a clean, readable dialogue. Your #1 job is to preserve each speaker's distinct \
voice and the conversational back-and-forth.

## Speakers
{speaker_list}

## Per-Speaker Style Profiles
{style_profile}

## KEEP these elements for EACH speaker:
- Their individual contractions, casual words, and verbal style
- Each speaker's characteristic phrases and personality
- The natural flow of conversation — agreements, disagreements, interruptions, humor
- Direct address between speakers ("yeah exactly", "wait, but...")
- Each speaker's level of formality (don't normalize everyone to the same register)
- Technical jargon each speaker actually uses

## NEVER do any of these:
- Merge speakers into one voice or remove attribution
- Convert dialogue into monologue
- Replace casual words with formal synonyms
- Add academic transition phrases
- Remove personality, humor, or opinions from any speaker
- Make all speakers sound the same
- Add filler like "It is worth noting" or "This is a testament to"
- Remove the back-and-forth conversational structure

## Structure guidance:
- Format as: **Speaker Name**: cleaned text...
- Add section headings (## Topic) when the conversation shifts to a new major topic
- Clean up verbal filler (um, uh, like, you know) and repetition
- Fix grammar only where it would be confusing in written form
- Keep paragraphs short — match conversational pacing
- Preserve the order of who speaks when
- Ignore any sponsor reads, advertisements, or promotional content"""

    few_shot_examples = """\
Here are examples of CORRECT vs INCORRECT multi-speaker conversion:

### Example transcript snippet:
**Host** [05:30]
so basically what happened is the company just they threw a ton of money at the problem and honestly it kinda worked like nobody expected that

**Guest** [05:45]
yeah I mean that's that's the crazy part right because everyone was saying oh this is never gonna work and then boom

### CORRECT conversion (preserves voices and dialogue):
## The Surprise Strategy

**Host**: So basically what happened is the company threw a ton of money at the problem, and honestly, it kinda worked. Like, nobody expected that.

**Guest**: Yeah, I mean, that's the crazy part, right? Because everyone was saying "oh, this is never gonna work" — and then boom.

### INCORRECT conversion (merged into monologue — DO NOT do this):
The company allocated substantial resources to address the challenge, and the strategy proved surprisingly effective. This outcome defied conventional expectations, as industry observers had been widely skeptical of the approach.

---"""

    result = _stream_message(
        client,
        model="claude-sonnet-4-5-20250929",
        max_tokens=16384,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"{few_shot_examples}\n\n"
                "Now convert this multi-speaker transcript into a clean dialogue. "
                "Preserve each speaker's distinct voice as described in the profiles above.\n\n"
                f"{transcript}"
            ),
        }],
    )

    return result


def transcript_to_essay(transcript: str, api_key: str | None = None) -> str:
    """Convert a transcript to an essay using Claude API.

    Detects single vs multi-speaker transcripts and uses the appropriate
    generation strategy. Multi-speaker transcripts (with **Speaker Name**
    markers) produce dialogue-style essays. Single-speaker transcripts
    produce monologue essays with the speaker's preserved voice.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    if _is_multi_speaker(transcript):
        return _transcript_to_essay_multi(transcript, client, api_key)
    return _transcript_to_essay_single(transcript, client, api_key)


def fetch_video_metadata(
    video_id: str, cookies_path: str | None = None
) -> dict[str, str | int]:
    """Fetch video metadata using yt-dlp --dump-json.

    Returns dict with title, description, channel, uploader, duration.
    """
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--remote-components", "ejs:github",
        "--dump-json", "--skip-download",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp metadata fetch failed.\nstderr: {result.stderr}"
        )

    meta = json.loads(result.stdout)
    return {
        "title": meta.get("title", ""),
        "description": meta.get("description", ""),
        "channel": meta.get("channel", ""),
        "uploader": meta.get("uploader", ""),
        "duration": meta.get("duration", 0),
    }


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


def download_video(
    video_id: str, output_path: Path, cookies_path: str | None = None
) -> Path:
    """Download a YouTube video using yt-dlp.

    Returns the path to the downloaded video file.
    """
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--remote-components", "ejs:github",
        "-o", str(output_path),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])

    print(f"Downloading video {video_id}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp video download failed.\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )

    # yt-dlp may add an extension — find the actual file
    parent = output_path.parent
    stem = output_path.stem
    candidates = sorted(parent.glob(f"{stem}.*"))
    if not candidates:
        raise RuntimeError(
            f"Download appeared to succeed but no file found matching {output_path}"
        )

    return candidates[0]
