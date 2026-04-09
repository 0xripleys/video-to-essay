"""Compare transcripts before/after misattribution fix across all multi-speaker videos.

Usage:
    uv run python scripts/eval_misattribution_fix.py

Downloads diarization data from S3, runs fix_misattributions on each multi-speaker
video, outputs an HTML diff viewer to scripts/eval_diff.html, and opens it.
"""

import html
import json
import os
import sys
import webbrowser

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg

from video_to_essay.diarize import fix_misattributions
from video_to_essay.s3 import download_file

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "eval_diff.html")


def get_multi_speaker_video_ids() -> list[dict]:
    """Query all processed videos and check which have multi-speaker transcripts."""
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "SELECT youtube_video_id, video_title FROM videos "
        "WHERE processed_at IS NOT NULL AND error IS NULL"
    )
    rows = cur.fetchall()
    conn.close()

    results = []
    for youtube_video_id, title in rows:
        try:
            content = download_file(youtube_video_id, "01_transcript/speaker_map.json")
            speaker_map = json.loads(content)
            results.append({
                "youtube_video_id": youtube_video_id,
                "title": title,
                "speaker_map": {int(k): v for k, v in speaker_map.items()},
            })
        except Exception:
            continue

    return results


def process_video(video: dict) -> list[dict]:
    """Run fix_misattributions on a video and return list of individual fixes."""
    vid = video["youtube_video_id"]
    speaker_map = video["speaker_map"]

    diarization = json.loads(download_file(vid, "01_transcript/diarization.json"))

    # Run fix and collect corrections by comparing before/after speaker IDs
    fixed = fix_misattributions(diarization, speaker_map)

    fixes = []
    for i, (orig, new) in enumerate(zip(diarization, fixed)):
        if orig["speaker"] != new["speaker"]:
            mins = int(orig["start"]) // 60
            secs = int(orig["start"]) % 60
            # Get surrounding context (1 segment before/after)
            context_before = None
            context_after = None
            if i > 0:
                cb = diarization[i - 1]
                cb_name = speaker_map.get(cb["speaker"], f"Speaker {cb['speaker']}")
                context_before = {"speaker": cb_name, "text": cb["text"]}
            if i < len(diarization) - 1:
                ca = diarization[i + 1]
                ca_name = speaker_map.get(ca["speaker"], f"Speaker {ca['speaker']}")
                context_after = {"speaker": ca_name, "text": ca["text"]}

            fixes.append({
                "index": i,
                "timestamp": f"{mins:02d}:{secs:02d}",
                "text": orig["text"],
                "from_speaker": speaker_map.get(orig["speaker"], f"Speaker {orig['speaker']}"),
                "to_speaker": speaker_map.get(new["speaker"], f"Speaker {new['speaker']}"),
                "context_before": context_before,
                "context_after": context_after,
            })

    return fixes


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def render_html(videos_data: list[dict]) -> str:
    """Render full HTML diff viewer."""
    nav_items = []
    sections = []

    for i, v in enumerate(videos_data):
        vid = v["youtube_video_id"]
        title = html.escape(v["title"] or "Untitled")
        speakers = ", ".join(v["speaker_map"].values())
        fixes = v["fixes"]
        num_fixes = len(fixes)
        anchor = f"video-{i}"

        badge = f'<span class="badge">{num_fixes} fix{"es" if num_fixes != 1 else ""}</span>' if num_fixes > 0 else '<span class="badge zero">no changes</span>'
        nav_items.append(f'<a href="#{anchor}">{title} {badge}</a>')

        cards_html = []
        for fix in fixes:
            ctx_before = ""
            if fix["context_before"]:
                cb = fix["context_before"]
                ctx_before = (
                    f'<div class="context">'
                    f'<span class="speaker-tag">{html.escape(cb["speaker"])}</span> '
                    f'{html.escape(_truncate(cb["text"]))}'
                    f'</div>'
                )
            ctx_after = ""
            if fix["context_after"]:
                ca = fix["context_after"]
                ctx_after = (
                    f'<div class="context">'
                    f'<span class="speaker-tag">{html.escape(ca["speaker"])}</span> '
                    f'{html.escape(_truncate(ca["text"]))}'
                    f'</div>'
                )

            cards_html.append(f"""
            <div class="fix-card">
                <div class="fix-header">
                    <span class="timestamp">[{fix["timestamp"]}]</span>
                    <span class="arrow-label">
                        <span class="from">{html.escape(fix["from_speaker"])}</span>
                        <span class="arrow">&rarr;</span>
                        <span class="to">{html.escape(fix["to_speaker"])}</span>
                    </span>
                </div>
                {ctx_before}
                <div class="fix-text">{html.escape(fix["text"])}</div>
                {ctx_after}
            </div>
            """)

        if not cards_html:
            content = '<p class="no-changes">No changes</p>'
        else:
            content = "".join(cards_html)

        sections.append(f"""
        <div class="video-section" id="{anchor}">
            <h2>{title}</h2>
            <p class="meta">
                <span class="vid">{vid}</span>
                <span class="speakers">{html.escape(speakers)}</span>
                {badge}
            </p>
            {content}
        </div>
        """)

    total_fixes = sum(len(v["fixes"]) for v in videos_data)
    total_videos = len(videos_data)
    changed = sum(1 for v in videos_data if v["fixes"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Misattribution Fix Eval</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; }}
.layout {{ display: flex; height: 100vh; }}
nav {{ width: 280px; min-width: 280px; background: #161b22; border-right: 1px solid #30363d; overflow-y: auto; padding: 16px 0; }}
nav h1 {{ font-size: 14px; padding: 0 16px 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
nav .summary {{ padding: 8px 16px 16px; font-size: 13px; color: #8b949e; border-bottom: 1px solid #30363d; margin-bottom: 8px; }}
nav a {{ display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; color: #c9d1d9; text-decoration: none; font-size: 13px; border-left: 3px solid transparent; }}
nav a:hover {{ background: #1c2128; border-left-color: #58a6ff; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #da3633; color: #fff; white-space: nowrap; }}
.badge.zero {{ background: #30363d; color: #8b949e; }}
main {{ flex: 1; overflow-y: auto; padding: 24px; }}
.video-section {{ margin-bottom: 48px; }}
.video-section h2 {{ font-size: 18px; margin-bottom: 8px; }}
.meta {{ font-size: 13px; color: #8b949e; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.vid {{ font-family: monospace; background: #1c2128; padding: 2px 6px; border-radius: 4px; }}
.fix-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
.fix-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }}
.timestamp {{ font-family: 'SF Mono', Monaco, monospace; font-size: 12px; color: #8b949e; background: #0d1117; padding: 2px 6px; border-radius: 4px; }}
.arrow-label {{ font-size: 14px; display: flex; align-items: center; gap: 6px; }}
.from {{ color: #ffa198; font-weight: 600; }}
.to {{ color: #7ee787; font-weight: 600; }}
.arrow {{ color: #8b949e; }}
.fix-text {{ font-size: 14px; line-height: 1.5; color: #e6edf3; padding: 10px 12px; background: #0d1117; border-radius: 6px; border-left: 3px solid #58a6ff; }}
.context {{ font-size: 12px; color: #6e7681; padding: 4px 12px; line-height: 1.4; }}
.context + .fix-text {{ margin-top: 6px; }}
.fix-text + .context {{ margin-top: 6px; }}
.speaker-tag {{ color: #8b949e; font-weight: 600; }}
.no-changes {{ color: #8b949e; font-style: italic; }}
@media (max-width: 700px) {{
    .layout {{ flex-direction: column; height: auto; }}
    nav {{ width: 100%; min-width: 0; max-height: 40vh; }}
    main {{ padding: 12px; }}
    .fix-card {{ padding: 12px; }}
    .fix-text {{ font-size: 13px; }}
}}
</style>
</head>
<body>
<div class="layout">
<nav>
    <h1>Eval: Misattribution Fix</h1>
    <div class="summary">{total_videos} videos, {changed} with changes, {total_fixes} total fixes</div>
    {"".join(nav_items)}
</nav>
<main>
    {"".join(sections)}
</main>
</div>
</body>
</html>"""


def main():
    print("Finding multi-speaker videos...")
    videos = get_multi_speaker_video_ids()
    print(f"Found {len(videos)} multi-speaker video(s)\n")

    if not videos:
        print("No multi-speaker videos to evaluate.")
        return

    videos_data = []
    for video in videos:
        title = video["title"] or "Untitled"
        speakers = list(video["speaker_map"].values())

        print(f"Processing: {title}")
        print(f"  Speakers: {', '.join(speakers)}")

        fixes = process_video(video)

        if not fixes:
            print("  No changes\n")
        else:
            print(f"  {len(fixes)} fixes\n")

        videos_data.append({
            **video,
            "fixes": fixes,
        })

    html_content = render_html(videos_data)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html_content)

    print(f"\nDiff viewer written to {OUTPUT_PATH}")
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
