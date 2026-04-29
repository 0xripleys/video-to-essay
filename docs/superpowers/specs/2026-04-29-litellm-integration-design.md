# LiteLLM Integration — Design

**Date:** 2026-04-29
**Status:** Approved, ready for implementation planning

## Goal

Make the Python pipeline model-agnostic by routing every LLM call through a thin wrapper around LiteLLM, so models can be swapped per task without rewriting domain code. This unlocks three use cases:

- **Cost optimization** — route specific tasks to cheaper providers (e.g., a small open-source model for sponsor filtering, Sonnet only where quality matters).
- **Future-proofing** — when a better/cheaper model lands, swap in a one-line config change instead of a code refactor.
- **Experimentation** — A/B test models per task on the same input to find the right model for each step.

Reliability/failover is explicitly **not** a goal. We are not designing for "Anthropic is down, fall over to OpenAI" — that's a different problem (would need fallback chains, retry-with-different-provider logic) and isn't pulling its weight today.

## Non-goals

- **Prompt caching** — high-value follow-up (especially for `scorer.py`, which makes 5 parallel calls with the same essay), but tracked separately to keep this spec focused.
- **Instructor / Pydantic-validated outputs** — when we want truly cross-provider structured output guarantees, layer it on top of `llm.complete`. Not now.
- **Hosted gateway** (Vercel AI Gateway, OpenRouter) — the wrapper sits at a layer where we can later route through a gateway by changing `litellm.api_base`. Defer until there's a concrete reason.
- **Web app LLM calls** — `web/` doesn't currently call LLMs. When it does, mirror this pattern in TypeScript (likely Vercel AI SDK).
- **End-to-end CI test** — separate spec; see Follow-ups.

## Why LiteLLM

Decision recap from brainstorming:

- **LiteLLM (Python library)** — provider-agnostic abstraction over ~100 LLM APIs with a unified interface. The 2025–2026 CVEs against LiteLLM all target the standalone proxy server (FastAPI app), not the in-process library. We use it as a library only.
- **vLLM** — different category (an inference engine for self-hosting open models). Out of scope.
- **OpenRouter** — a hosted gateway, not a library. Optional later layer; LiteLLM can route to it if needed.

## Architecture

A single new module — `src/video_to_essay/llm.py` — is the **only** place that imports `litellm`. Every domain module (`transcriber.py`, `place_images.py`, `scorer.py`, `extract_frames.py`, `filter_sponsors.py`, `diarize.py`, `summarize.py`) imports `from video_to_essay import llm` and calls into it.

```
domain modules ──► llm.py ──► litellm ──► provider API
                     │  │
                     │  └── persist: runs/<video_id>/<step>/llm_calls/*.json
                     │      (CLI: local disk; worker: S3 via existing run-dir sync)
                     │
                     └── MODELS dict (per-task defaults)
```

The wrapper is a thin function layer. It does **not** parse responses, manage prompts, or enforce schemas. Call sites keep ownership of their prompt assembly and output parsing. The wrapper *does* own one cross-cutting concern: persisting every call's input/output as JSON for debugging and replay (Section 7).

## 1. The wrapper module

`src/video_to_essay/llm.py`:

```python
"""Single entry point for all LLM calls in the pipeline.

Models are selected per-task. Defaults live in MODELS below. Pass `model=`
explicitly to override (used by the --model CLI flag for experimentation).
"""

import litellm
from litellm import ModelResponse

# Canonical model assignments. Edit here for permanent swaps.
MODELS: dict[str, str] = {
    "essay_single":   "anthropic/claude-sonnet-4-5-20250929",
    "essay_multi":    "anthropic/claude-sonnet-4-5-20250929",
    "style_profile":  "anthropic/claude-haiku-4-5-20251001",
    "sponsor_filter": "anthropic/claude-haiku-4-5-20251001",
    "frame_classify": "anthropic/claude-haiku-4-5-20251001",
    "diarize_helper": "anthropic/claude-haiku-4-5-20251001",
    "place_images":   "anthropic/claude-sonnet-4-5-20250929",
    "score":          "anthropic/claude-sonnet-4-5-20250929",
    "summarize":      "anthropic/claude-sonnet-4-5-20250929",
}


def complete(
    task: str,
    messages: list[dict],
    *,
    model: str | None = None,
    **kwargs: object,
) -> ModelResponse:
    """Non-streaming LLM call. Returns the full litellm ModelResponse."""
    resolved = model or MODELS[task]
    return litellm.completion(model=resolved, messages=messages, **kwargs)


def stream(
    task: str,
    messages: list[dict],
    *,
    model: str | None = None,
    **kwargs: object,
):
    """Streaming LLM call. Yields delta strings.

    Used for long-running essay/place_images requests to avoid
    the non-streaming long-request timeout (~10 min).
    """
    resolved = model or MODELS[task]
    response = litellm.completion(model=resolved, messages=messages, stream=True, **kwargs)
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

**Why two functions:** call sites that stream today (`place_images.py:_stream_message`, `transcriber.py:_stream_message`) accumulate chunks into a string and discard incremental output — they use streaming purely to dodge the long-request timeout. Keeping `stream()` separate lets us preserve that behavior with a one-line consumer (`text = "".join(llm.stream(...))`) without each call site re-implementing chunk extraction.

**Tool use, vision, cache_control:** all passed through via `**kwargs` and message content. The wrapper does not introspect them.

**Provider auth:** LiteLLM reads provider keys from env (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.). No code change to `.env` plumbing — Anthropic key is already there; users add others as they experiment.

**Dependency:** add `litellm>=1.83.7` to `pyproject.toml`. The 1.83.7 floor is a deliberate hedge against the 2025–2026 proxy CVEs (none affect the library, but pinning above the fix line costs nothing).

## 2. CLI flag wiring

The single-step subcommands in `main.py` each gain a `--model` / `-m` option that overrides the default for the LLM call(s) in that step:

| Subcommand | LLM tasks invoked | Notes |
|---|---|---|
| `diarize` | `diarize_helper` | New flag |
| `filter-sponsors` | `sponsor_filter` | New flag |
| `essay` | `style_profile`, `essay_single` or `essay_multi`, `summarize` | Flag applies to essay generation only (the primary task); style_profile and summarize use their `MODELS` defaults |
| `extract-frames` | `frame_classify` | New flag |
| `place-images` | `place_images` | New flag |
| `score` | `score` | **Already has** `--model` flag (Anthropic-only string default). Migration changes default to `None` and accepts litellm model strings |
| `score-dimension` | `score` | Same as `score` |

The `transcript` and `download` subcommands don't invoke LLMs (they call Deepgram and yt-dlp respectively) — no flag.

`summarize.py` is a library module called from the `essay` subcommand and `process_worker.py` — there's no standalone `summarize` subcommand. Per-task swapping for summarize means editing `MODELS["summarize"]`.

```python
@app.command()
def essay(
    video_id: str,
    model: str | None = typer.Option(None, "--model", "-m",
        help="Override the model for essay generation (e.g. openai/gpt-5)"),
    ...
):
    ...
    transcriber.generate_essay(transcript, ..., model=model)
```

Each step function in the domain modules gains a `model: str | None = None` parameter that's threaded into `llm.complete(task=..., model=model)`. When `model=None`, the wrapper uses the `MODELS` default.

The full-pipeline `run` command does **not** get `--model` — too many tasks to disambiguate from one flag. To swap one task across a full run, edit `MODELS`. To experiment on one step, use the single-step CLI on a pre-staged video.

## 3. Streaming, tool use, and response shapes

**Where streaming is used today:**
- `transcriber.py:_stream_message` — wraps essay generation (single + multi speaker)
- `place_images.py:_stream_message` — wraps the Sonnet image-placement call

Both helpers do the same thing: collect chunks, join them, return the full string. **No call site consumes chunks incrementally.** Streaming exists purely as a workaround for Anthropic's long-request timeout. Post-migration, both helpers are deleted; their callers do `text = "".join(llm.stream(task=..., messages=...))`.

**Tool use:** `scorer.py` and `extract_frames.py` use Anthropic's tool-use format for structured outputs. LiteLLM normalizes tool calls across providers. Anthropic's `msg.content[0].input` (parsed dict) becomes `response.choices[0].message.tool_calls[0].function.arguments` (JSON string — call sites add `json.loads`).

**Vision:** `extract_frames.py` sends image content blocks. LiteLLM accepts the OpenAI-style `{"type": "image_url", "image_url": {"url": "data:..."}}` format and translates per-provider. Anthropic's native `{"type": "image", "source": {...}}` format also works for Anthropic models. Migration uses the OpenAI-style for portability.

**Response shape mapping (Anthropic SDK → LiteLLM):**

| Anthropic | LiteLLM |
|---|---|
| `msg.content[0].text` | `response.choices[0].message.content` |
| `msg.content[0].input` (tool use, dict) | `json.loads(response.choices[0].message.tool_calls[0].function.arguments)` |
| `msg.usage.input_tokens` / `output_tokens` | `response.usage.prompt_tokens` / `completion_tokens` |
| `msg.stop_reason` | `response.choices[0].finish_reason` |

## 4. Rate-limit retries

`place_images.py` currently has bespoke exponential backoff on `anthropic.RateLimitError` (5 attempts, 15s/30s/60s/120s waits). Post-migration: pass `num_retries=5` to `llm.complete` for that call. LiteLLM owns retries and applies them uniformly across providers.

`scorer.py` also has retry logic on `anthropic.RateLimitError`. Same treatment — pass `num_retries` through.

The bespoke retry logic (the retry loop inside `place_images._stream_message`, and `scorer._api_call_with_retry`) gets deleted along with the helpers themselves.

## 5. Migration plan

Incremental, one module per PR. Each PR is self-contained: code change + manual smoke test on a known video.

**Order (cheapest → most complex):**

| # | Module | Why this slot |
|---|---|---|
| 1 | `summarize.py` | Single `messages.create`, no streaming, no tool use. Canary for the wrapper shape. |
| 2 | `filter_sponsors.py` | Single call, text in/out. |
| 3 | `diarize.py` | Single call, helper for speaker labeling. |
| 4 | `extract_frames.py` | Vision input + tool use. First non-trivial conversion. |
| 5 | `scorer.py` | Five parallel calls + tool use. Rewrite the one existing test. |
| 6 | `transcriber.py` | Streaming via `_stream_message` + Haiku style profile. |
| 7 | `place_images.py` | Streaming + JSON output + retry/backoff. Most logic-heavy. |

**Per-module checklist (PR description):**

- [ ] Replace `import anthropic` with `from video_to_essay import llm`
- [ ] `client.messages.create(model=..., ...)` → `llm.complete(task="<key>", ...)`
- [ ] `_stream_message(...)` → `"".join(llm.stream(task="<key>", ...))` and delete the helper
- [ ] Map response shape: `.content[0].text` → `.choices[0].message.content`; tool-use `.input` → `json.loads(.tool_calls[0].function.arguments)`
- [ ] Vision message blocks: convert Anthropic-native to OpenAI-style image blocks (only `extract_frames.py`)
- [ ] Replace `try/except anthropic.RateLimitError` with `num_retries=5` kwarg to `llm.complete`
- [ ] Add `model: str | None = None` parameter to the public step function and thread through to `llm.complete`
- [ ] Wrap the step's body in `with llm.run_context(step_dir):` so calls persist into `<step_dir>/llm_calls/`
- [ ] Add `--model` flag to the corresponding `main.py` CLI subcommand
- [ ] Smoke test: run the step on a stable video pre- and post-change, diff outputs *and* verify `llm_calls/*.json` files were written

**Cleanup PR (final):** remove `anthropic` from `pyproject.toml` direct dependencies (it stays as a transitive dep via litellm).

## 6. Test strategy

Coverage of LLM call paths is thin today. Survey:

| Module | Tests | LLM call covered? |
|---|---|---|
| `summarize.py` | 3 | ❌ Only `_strip_takeaways` |
| `filter_sponsors.py` | 5 | ❌ Only parsing helpers |
| `diarize.py` | 4 | ❌ Only `_format_transcript` |
| `extract_frames.py` | 11 | ❌ Pure helpers only |
| `scorer.py` | 1 | ✅ `test_score_essay_return_shape` |
| `transcriber.py` | 6 | ❌ URL/speaker parsing only |
| `place_images.py` | 9 | ❌ Frame formatting/embedding only |

**Implication:** existing tests (which test pure helpers) won't break, because they don't touch LLM calls. But they also won't validate the migration. We rely on **manual smoke testing per module**:

1. Pick one stable video ID with cached `runs/<video_id>/` artifacts on disk.
2. Pre-migration: run the affected step, save output to `runs/<video_id>-pre/`.
3. Post-migration: run again, save to `runs/<video_id>-post/`.
4. Diff. Deterministic outputs (sponsor ranges, frame classifications) should match modulo whitespace. Stochastic outputs (essays, scores) get an eyeball review for "different but equivalent."

**The one existing LLM-mocking test (`test_scorer.py`):** rewrite to `patch("video_to_essay.scorer.llm.complete", ...)` returning a litellm-shaped `ModelResponse` mock. Keep the assertion (`test_score_essay_return_shape`).

No new unit tests as part of the migration. The next section captures the regression-net work as a follow-up.

## 7. Persisting LLM calls

Every LLM call is persisted as a JSON file inside the step's run directory:

```
runs/<video_id>/03_essay/
├── essay.md                              (existing output)
└── llm_calls/                            (new)
    ├── style_profile_<timestamp>.json
    └── essay_single_<timestamp>.json
```

The worker pipeline already syncs the run directory to S3, so the same structure lands at `s3://<bucket>/runs/<video_id>/03_essay/llm_calls/...` with no extra plumbing. CLI runs leave the JSON on local disk only.

### File format

```json
{
  "task": "score",
  "model": "anthropic/claude-sonnet-4-5-20250929",
  "timestamp_ms": 1746029067123,
  "request_id": "req_011CaYamezDcqDaoMxriQcDQ",
  "input_tokens": 4321,
  "output_tokens": 215,
  "messages": [...],
  "kwargs": {"tools": [...], "max_tokens": 1024},
  "response": {...}
}
```

`request_id` is pulled from litellm's response metadata (the same `req_...` ID that appears in the Anthropic Console logs page) so calls can be correlated to provider-side logs.

### Plumbing — context-managed persistence

The wrapper exposes a `run_context` context manager. Each step function opens it once with the step's directory; every `llm.complete(...)` inside automatically writes its JSON to that directory.

```python
# llm.py additions
import contextvars
from contextlib import contextmanager
from pathlib import Path

_step_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar("step_dir", default=None)

@contextmanager
def run_context(step_dir: Path):
    """Persist all LLM calls inside this block to step_dir/llm_calls/."""
    token = _step_dir.set(step_dir)
    try:
        yield
    finally:
        _step_dir.reset(token)


def complete(task, messages, *, model=None, **kwargs):
    resolved = model or MODELS[task]
    response = litellm.completion(model=resolved, messages=messages, **kwargs)
    _persist(task, messages, kwargs, response)
    return response
```

```python
# transcriber.py (example call site)
def generate_essay(transcript, ..., run_dir: Path, model=None):
    with llm.run_context(run_dir / "03_essay"):
        ...
        response = llm.complete(task="essay_single", messages=messages, model=model)
```

When `run_context` is not set (e.g., during tests), `_persist` is a no-op. Tests don't need to mock the persistence layer.

`contextvars` are inherited by `concurrent.futures.ThreadPoolExecutor` workers automatically when the executor is created inside the context, so `scorer.py`'s 5 parallel dimension calls all persist correctly without extra wiring.

### Image stripping (the vision gotcha)

`extract_frames.py` sends base64-encoded image bytes inside messages. Persisting the literal request would redundantly store ~10–30 MB of frames per video — frames the worker has already uploaded to S3.

Before persisting, `_persist` walks the messages and replaces any `image_url` data URL with a reference:

```python
{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ..."}}
# becomes
{"type": "image_url", "image_url": {"url": "<base64 image, sha256:abc123, 142kb>"}}
```

If the frame's S3 URL is already known to the call site, callers may pre-rewrite to `image_url: {"url": "https://.../frame_0042.jpg"}` instead — the wrapper passes that through unchanged.

### Storage volume

After image stripping, expected per-video footprint is ~1–3 MB of JSON across all calls. At 1k videos/month, ~2 GB/month total → well under $0.10/month on S3.

### Read path (debug/inspection)

The runs viewer (separate spec) is a natural consumer: a "LLM calls" tab per step that lists files in `runs/<video_id>/<step>/llm_calls/` and renders the JSON. No DB row needed; just S3 directory listings.

## 8. Follow-ups (not part of this work)

These are flagged here so they don't get lost but are explicitly out of scope for this spec:

- **End-to-end CI test in GitHub Actions.** Add a job that runs `video-to-essay run <pinned_url>` against a stable video, hitting real LLM endpoints. Likely:
  - Gated behind `workflow_dispatch` or scheduled nightly to avoid per-PR cost
  - Repo secrets for `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, `YOUTUBE_API_KEY`
  - Tolerant assertions (essay length > N, expected sections present, no exceptions)
  - Estimated cost ~$0.50–$1 per run with current models
  - Design questions (cost gating, flake handling, what to assert) deserve their own spec.
- **Prompt caching for `scorer.py` and `place_images.py`** — high-value cost win, especially for the 5-parallel scorer pattern.
- **Instructor / Pydantic outputs** for tool-use call sites once we want cross-provider schema guarantees.

## Open risks

- **Stochastic outputs make smoke-test diffing subjective.** Mitigation: do the diff on at least two videos per module, look for *structural* equivalence (same number of sections, same image placements, etc.) rather than identical text.
- **LiteLLM lags newest provider features by days/weeks.** Acceptable — we don't depend on bleeding-edge features today, and the wrapper exposes `**kwargs` so any provider-specific param we need can pass through.
- **`cache_control` is Anthropic-flavored.** When we add caching to `scorer.py` (follow-up), the cache hint becomes a no-op if the task is later swapped to OpenAI/Gemini. Acceptable — caching is an optimization, not correctness.
