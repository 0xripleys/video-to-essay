# Essay Summary Step

## Overview

Add a post-processing step that reads a generated essay, extracts 3-5 key takeaway bullets via a separate LLM call, and prepends them as a `## Key Takeaways` section right after the H1 title.

## Where It Runs

Inside step 03 (essay), after `transcriber.py` finishes. Both the CLI (`main.py`) and the worker (`process_worker.py`) call it as a sub-step. Output overwrites the same essay file in `03_essay/`.

## New Module: `summarize.py`

A new file at `src/video_to_essay/summarize.py` with a single public function:

```python
def summarize_essay(essay_path: Path, force: bool = False) -> None
```

- Reads the essay markdown from `essay_path`
- If a `## Key Takeaways` section already exists and `force` is False, skips (idempotent)
- Makes a Claude API call to extract 3-5 key takeaway bullets
- Prepends the section after the H1 title and overwrites the file

### LLM Call

- Model: Sonnet (`claude-sonnet-4-5-20250929`)
- Input: The full essay text
- Output: 3-5 bullet points as a simple markdown list
- System prompt: Be concise, focus on the video's main arguments/findings, no fluff, no "In this video..." phrasing

### Output Format

```markdown
# Video Title Here

## Key Takeaways

- First key point
- Second key point
- Third key point

(rest of essay continues...)
```

## Files Changed

| File | Change |
|------|--------|
| `src/video_to_essay/summarize.py` | **New.** Module with `summarize_essay()` function |
| `src/video_to_essay/main.py` | Call `summarize_essay()` after the essay step |
| `src/video_to_essay/process_worker.py` | Call `summarize_essay()` after essay generation |

## Edge Cases

- Short essays (<500 chars): still generate a summary
- Idempotency: if `## Key Takeaways` already exists, skip unless `--force`
