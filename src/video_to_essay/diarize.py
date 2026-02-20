"""
Deepgram-based transcription with speaker diarization.

Uses Deepgram Nova-3 for transcription with speaker diarization.
Requires DEEPGRAM_API_KEY — raises RuntimeError if missing.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import anthropic
import httpx

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"


def _load_env() -> None:
    """Load .env file from project root if it exists."""
    # Walk up from this file to find .env
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def extract_audio(video_path: Path, output_dir: Path) -> Path:
    """Extract audio from video file using ffmpeg.

    Returns path to the extracted MP3 file.
    """
    audio_path = output_dir / "audio.mp3"
    if audio_path.exists():
        print(f"Audio exists, skipping ({audio_path})")
        return audio_path

    print(f"Extracting audio from {video_path.name}...")
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn", "-acodec", "libmp3lame", "-q:a", "2",
        str(audio_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg audio extraction failed.\nstderr: {result.stderr}"
        )

    print(f"Audio extracted -> {audio_path}")
    return audio_path


def run_diarization(
    audio_path: Path, api_key: str, output_dir: Path
) -> list[dict]:
    """Run Deepgram speaker diarization via API.

    Sends audio to Deepgram Nova-3 with diarize=true and utterances=true.
    Returns list of utterances with speaker IDs.
    Saves diarization.json and deepgram_response.json.
    """
    diarization_path = output_dir / "diarization.json"
    if diarization_path.exists():
        print(f"Diarization exists, skipping ({diarization_path})")
        return json.loads(diarization_path.read_text())

    size_mb = audio_path.stat().st_size / 1_000_000
    print(f"Uploading {audio_path.name} to Deepgram ({size_mb:.1f} MB)...")

    audio_data = audio_path.read_bytes()

    response = httpx.post(
        DEEPGRAM_API_URL,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/mpeg",
        },
        params={
            "model": "nova-3",
            "smart_format": "true",
            "utterances": "true",
            "diarize": "true",
        },
        content=audio_data,
        timeout=300.0,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Deepgram API error {response.status_code}: {response.text[:500]}"
        )

    result = response.json()

    # Save full response for debugging
    full_response_path = output_dir / "deepgram_response.json"
    full_response_path.write_text(json.dumps(result, indent=2))
    print(f"Full Deepgram response saved -> {full_response_path}")

    # Extract utterances
    utterances = result.get("results", {}).get("utterances", [])
    segments: list[dict] = []
    for utt in utterances:
        segments.append({
            "start": round(utt["start"], 2),
            "end": round(utt["end"], 2),
            "speaker": utt["speaker"],
            "text": utt["transcript"],
        })

    diarization_path.write_text(json.dumps(segments, indent=2))
    unique_speakers = set(s["speaker"] for s in segments)
    print(
        f"Diarization saved ({len(segments)} utterances, "
        f"{len(unique_speakers)} speakers) -> {diarization_path}"
    )

    return segments


def map_speaker_names(
    segments: list[dict], metadata: dict, output_dir: Path
) -> dict[int, str]:
    """Use Claude Haiku to map speaker IDs to real names.

    Only called when there are multiple speakers. Sends first ~80 utterances
    plus video metadata for context.
    """
    mapping_path = output_dir / "speaker_map.json"
    if mapping_path.exists():
        print(f"Speaker mapping exists, skipping ({mapping_path})")
        raw = json.loads(mapping_path.read_text())
        return {int(k): v for k, v in raw.items()}

    # Build sample of attributed transcript
    sample_lines: list[str] = []
    for seg in segments[:80]:
        mins = int(seg["start"]) // 60
        secs = int(seg["start"]) % 60
        sample_lines.append(
            f"[{mins:02d}:{secs:02d}] Speaker {seg['speaker']}: {seg['text']}"
        )
    sample_text = "\n".join(sample_lines)

    speaker_ids = sorted(set(s["speaker"] for s in segments if s["speaker"] >= 0))

    prompt = f"""\
I have a diarized podcast transcript where speakers are labeled with numeric IDs.
Using the video metadata and conversational context, map each speaker ID to their real name.

## Video metadata
- Title: {metadata.get('title', 'N/A')}
- Channel: {metadata.get('channel', 'N/A')}
- Description (first 1500 chars):
{metadata.get('description', 'N/A')[:1500]}

## Speaker IDs found: {', '.join(str(s) for s in speaker_ids)}

## First ~80 lines of diarized transcript:
{sample_text}

## Instructions
1. Look at the video title, description, and channel for speaker names.
2. Use conversational cues (who introduces the show, who says "welcome back",
   who is interviewed vs interviewing) to match IDs to names.
3. Return a JSON object mapping each speaker ID (as string key) to a real name.
   If you can't confidently identify a speaker, use "Speaker N".

Return ONLY a valid JSON object, no other text. Example:
{{"0": "Tyler Neville", "1": "Quinn Thompson", "2": "Felix Jauvin"}}"""

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = msg.content[0].text.strip()
    # Extract JSON from response (in case Haiku wraps it in markdown)
    json_match = re.search(r"\{[^}]+\}", response_text, re.DOTALL)
    if json_match:
        raw_mapping = json.loads(json_match.group())
    else:
        print(
            f"WARNING: Could not parse speaker mapping from Haiku response:\n"
            f"{response_text}"
        )
        raw_mapping = {str(s): f"Speaker {s}" for s in speaker_ids}

    mapping_path.write_text(json.dumps(raw_mapping, indent=2))

    mapping = {int(k): v for k, v in raw_mapping.items()}
    print(f"Speaker mapping: {mapping}")
    return mapping


def format_transcript(
    segments: list[dict], speaker_names: dict[int, str] | None = None
) -> str:
    """Format Deepgram utterances into readable transcript.

    Groups consecutive utterances by same speaker.
    If speaker_names provided (multi-speaker): **Speaker Name** [MM:SS] format.
    If single speaker: [MM:SS] Text format (matches YouTube transcript format).
    """
    if not segments:
        return ""

    blocks: list[str] = []
    current_speaker: int | None = None
    current_texts: list[str] = []
    current_start: float = 0.0

    for seg in segments:
        speaker_id = seg["speaker"]

        if speaker_id != current_speaker:
            # Flush previous block
            if current_speaker is not None and current_texts:
                mins = int(current_start) // 60
                secs = int(current_start) % 60
                text = " ".join(current_texts)
                if speaker_names:
                    name = speaker_names.get(
                        current_speaker, f"Speaker {current_speaker}"
                    )
                    blocks.append(f"**{name}** [{mins:02d}:{secs:02d}]\n{text}")
                else:
                    blocks.append(f"[{mins:02d}:{secs:02d}] {text}")

            current_speaker = speaker_id
            current_texts = [seg["text"]]
            current_start = seg["start"]
        else:
            current_texts.append(seg["text"])

    # Flush last block
    if current_speaker is not None and current_texts:
        mins = int(current_start) // 60
        secs = int(current_start) % 60
        text = " ".join(current_texts)
        if speaker_names:
            name = speaker_names.get(current_speaker, f"Speaker {current_speaker}")
            blocks.append(f"**{name}** [{mins:02d}:{secs:02d}]\n{text}")
        else:
            blocks.append(f"[{mins:02d}:{secs:02d}] {text}")

    return "\n\n".join(blocks)


def transcribe_with_deepgram(
    run_dir: Path,
    metadata: dict,
    force: bool = False,
) -> None:
    """Top-level orchestrator for Deepgram transcription + diarization.

    Requires DEEPGRAM_API_KEY in environment or .env file.
    Raises RuntimeError if the key is missing.
    Always writes to transcript.txt (with **Speaker** markers if multi-speaker).
    """
    _load_env()
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DEEPGRAM_API_KEY not set. Set it in .env or environment. "
            "Get a free key at https://console.deepgram.com/signup"
        )

    # Check for existing output (skip if not forcing)
    transcript_path = run_dir / "transcript.txt"
    if not force and transcript_path.exists():
        print(f"Transcript exists, skipping ({transcript_path})")
        return

    # Step 1: Find video file
    video_files = sorted(run_dir.glob("video.*"))
    if not video_files:
        raise RuntimeError(
            f"No video file in {run_dir} — run download step first"
        )
    video_path = video_files[0]

    # Step 2: Extract audio from video
    print("Extracting audio from video...")
    audio_path = extract_audio(video_path, run_dir)

    # Step 3: Run Deepgram diarization
    print("Running Deepgram diarization...")
    segments = run_diarization(audio_path, api_key, run_dir)

    # Step 4: Check speaker count
    unique_speakers = set(s["speaker"] for s in segments)
    is_multi_speaker = len(unique_speakers) > 1

    # Step 5: Map speaker names (only if multi-speaker)
    speaker_names: dict[int, str] | None = None
    if is_multi_speaker:
        print(f"Found {len(unique_speakers)} speakers, mapping names...")
        speaker_names = map_speaker_names(segments, metadata, run_dir)

    # Step 6: Format and save transcript
    transcript_text = format_transcript(segments, speaker_names)
    transcript_path.write_text(transcript_text)
    print(f"Transcript saved ({len(transcript_text)} chars) -> {transcript_path}")
