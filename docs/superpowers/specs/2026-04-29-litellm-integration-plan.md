# Implementation Plan: LiteLLM Integration

Based on: `docs/superpowers/specs/2026-04-29-litellm-integration-design.md`

Nine sequenced PRs. Phase 0 lays the foundation; Phases 1–7 migrate one module each (cheapest → most complex); Phase 8 is cleanup.

Each phase ships independently. After Phase 0, the codebase has both `anthropic.Anthropic` call sites and `llm.complete` call sites side-by-side until cleanup — that's expected.

---

## Phase 0 — Wrapper foundation

Lay down `llm.py`. No call site changes. End state: `llm.py` works end-to-end against Anthropic but nothing imports it yet.

### Steps

1. **Add dependency**: `uv add 'litellm>=1.83.7'`

2. **Create `src/video_to_essay/llm.py`**:
   - `MODELS: dict[str, str]` — nine task → litellm-model-string entries (copy from spec §1)
   - `complete(task, messages, *, model=None, **kwargs) -> ModelResponse` — resolves model, calls `litellm.completion`, then `_persist`
   - `stream(task, messages, *, model=None, **kwargs)` — generator yielding delta strings; also persists the assembled response after the stream drains
   - `run_context(step_dir: Path)` — context manager that sets `_step_dir` ContextVar; resets on exit
   - `_persist(task, messages, kwargs, response)` — writes `{step_dir}/llm_calls/{task}_{ms_timestamp}.json` if `_step_dir` is set, no-op otherwise. Calls `_strip_image_bytes(messages)` first.
   - `_strip_image_bytes(messages)` — walks message content blocks, replaces `image_url.url` data URLs with `<base64 image, sha256:..., {kb}kb>` reference strings. Leaves `https://...` URLs alone.
   - `_extract_request_id(response)` — pull provider request ID from `response._hidden_params` if present (LiteLLM exposes Anthropic's `request-id` header there); store in persisted JSON.

3. **Add unit tests** in `tests/test_llm.py`:
   - `test_strip_image_bytes_replaces_data_url` — pure function, no LLM
   - `test_strip_image_bytes_preserves_https_url`
   - `test_strip_image_bytes_handles_text_only_messages`
   - `test_persist_writes_json_when_context_set` (use `tmp_path`)
   - `test_persist_noop_when_context_unset`
   - `test_run_context_resets_after_exit`
   - `test_complete_resolves_model_from_models_dict` — patch `litellm.completion`, assert resolved model passed
   - `test_complete_uses_explicit_override` — patch `litellm.completion`, pass `model=...`, assert override wins

4. **Smoke test manually** (not in CI):
   ```bash
   uv run python -c "
   from pathlib import Path
   from video_to_essay import llm
   r = llm.complete(task='summarize', messages=[{'role':'user','content':'Say hi'}])
   print(r.choices[0].message.content)
   "
   ```

### Files touched
- `pyproject.toml` (add litellm)
- `src/video_to_essay/llm.py` (new)
- `tests/test_llm.py` (new)

---

## Phase 1 — Migrate `summarize.py` (canary)

Single non-streaming call. Validates the wrapper shape before tackling harder modules.

### Steps

1. **Edit `src/video_to_essay/summarize.py`**:
   - Replace `import anthropic` with `from video_to_essay import llm`
   - Replace `client = anthropic.Anthropic()` + `client.messages.create(...)` with `llm.complete(task="summarize", messages=..., max_tokens=...)`
   - Replace `msg.content[0].text` with `response.choices[0].message.content`
   - Add `model: str | None = None` parameter to `summarize_essay()`, pass to `llm.complete`
   - Wrap call in `with llm.run_context(essay_path.parent):` so the JSON lands in `runs/<video_id>/03_essay/llm_calls/`

2. **No CLI flag** — `summarize` has no standalone subcommand. Skip.

3. **Smoke test**:
   ```bash
   # Pre-migration baseline (do this on the previous commit if needed)
   video-to-essay essay <stable_video_id> --force
   cp runs/<id>/03_essay/essay_summary.md /tmp/pre.md

   # Post-migration
   video-to-essay essay <stable_video_id> --force
   diff /tmp/pre.md runs/<id>/03_essay/essay_summary.md
   ls runs/<id>/03_essay/llm_calls/  # should contain summarize_<ts>.json
   ```

### Files touched
- `src/video_to_essay/summarize.py`

---

## Phase 2 — Migrate `filter_sponsors.py`

Single text-in/text-out call.

### Steps

1. **Edit `src/video_to_essay/filter_sponsors.py`**:
   - Same pattern as Phase 1
   - Task key: `sponsor_filter`
   - Add `model` parameter to the public function
   - Wrap in `llm.run_context(<step_dir>)`

2. **Edit `src/video_to_essay/main.py`**:
   - Add `--model` / `-m` option to `filter_sponsors_cmd` (the `filter-sponsors` subcommand)
   - Thread to the function

3. **Smoke test**: re-run `filter-sponsors` step on a stable video; sponsor ranges should be identical or near-identical.

### Files touched
- `src/video_to_essay/filter_sponsors.py`
- `src/video_to_essay/main.py`

---

## Phase 3 — Migrate `diarize.py`

Single call, helper for speaker labeling.

### Steps

1. **Edit `src/video_to_essay/diarize.py`**:
   - Same pattern
   - Task key: `diarize_helper`
   - Wrap in `llm.run_context(<step_dir>)`

2. **Edit `src/video_to_essay/main.py`**:
   - Add `--model` to the `diarize` subcommand

3. **Smoke test**: re-run on a multi-speaker video; speaker labels should match.

### Files touched
- `src/video_to_essay/diarize.py`
- `src/video_to_essay/main.py`

---

## Phase 4 — Migrate `extract_frames.py` (vision + tool use)

First non-trivial conversion.

### Steps

1. **Edit `src/video_to_essay/extract_frames.py`**:
   - Convert image content blocks from Anthropic-native format to OpenAI-style:
     ```python
     # Before: {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
     # After:  {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
     ```
   - Replace `client.messages.create(model=..., tools=[...], tool_choice=..., messages=...)` with `llm.complete(task="frame_classify", messages=..., tools=[...], tool_choice=..., max_tokens=...)`
   - Map tool output: `msg.content[0].input` (dict) → `json.loads(response.choices[0].message.tool_calls[0].function.arguments)`
   - Add `model` parameter
   - Wrap in `llm.run_context(<step_dir>)` — the ContextVar is inherited by ThreadPoolExecutor workers automatically

2. **Edit `src/video_to_essay/main.py`**:
   - Add `--model` to the `extract-frames` subcommand

3. **Smoke test**: re-run on a video with mixed frames; classifications should be near-identical (some non-determinism is acceptable). Verify `llm_calls/` contains one JSON per frame.

### Files touched
- `src/video_to_essay/extract_frames.py`
- `src/video_to_essay/main.py`

---

## Phase 5 — Migrate `scorer.py` (parallel calls + tool use)

Bulk of the test rewrite work lives here.

### Steps

1. **Edit `src/video_to_essay/scorer.py`**:
   - Delete `_api_call_with_retry` helper
   - Replace `client.messages.create(...)` calls with `llm.complete(task="score", ..., num_retries=5)`
   - Map tool output (same as Phase 4): `.input` → `json.loads(.tool_calls[0].function.arguments)`
   - Drop `client` parameter from internal helpers; the wrapper handles client construction
   - Add `model` parameter to `score_essay` and `score_one`, thread through
   - Wrap each top-level entry point (`score_essay`, `score_one`) in `llm.run_context(<step_dir>)` — ThreadPoolExecutor inherits the ContextVar
   - Remove the existing `--model` default value (`DEFAULT_MODEL = "claude-sonnet-4-5-20250929"`); the new default is `None` and `MODELS["score"]` resolves it

2. **Edit `src/video_to_essay/main.py`**:
   - Update `score` and `score-dimension` subcommands: change `--model` default from the Anthropic string to `None`, update help text to say "litellm model string (e.g. openai/gpt-5)"

3. **Rewrite `tests/test_scorer.py`**:
   - Replace `patch("video_to_essay.scorer.anthropic.Anthropic", return_value=mock_client)` with `patch("video_to_essay.scorer.llm.complete", return_value=mock_response)`
   - Build a litellm-shaped `ModelResponse` mock instead of an Anthropic Message mock:
     ```python
     mock_response = MagicMock()
     mock_response.choices = [MagicMock()]
     mock_response.choices[0].message.tool_calls = [MagicMock()]
     mock_response.choices[0].message.tool_calls[0].function.arguments = json.dumps(mock_dimension_result)
     ```
   - Keep the existing `test_score_essay_return_shape` assertion

4. **Smoke test**: score an existing essay, compare scores to a baseline. Stochastic — eyeball for "in the same ballpark."

### Files touched
- `src/video_to_essay/scorer.py`
- `src/video_to_essay/main.py`
- `tests/test_scorer.py`

---

## Phase 6 — Migrate `transcriber.py` (streaming)

### Steps

1. **Edit `src/video_to_essay/transcriber.py`**:
   - Delete `_stream_message` helper
   - Replace `_stream_message(client, model="claude-sonnet-...", messages=...)` with `"".join(llm.stream(task="essay_single" or "essay_multi", messages=...))`
   - Replace the Haiku `extract_style_profile` call (`client.messages.create`) with `llm.complete(task="style_profile", messages=...)`
   - Drop `client` and `api_key` parameters from the public API where possible (LiteLLM uses env vars directly)
   - Add `model` parameter to `generate_essay` and other public entry points
   - Wrap each top-level call in `llm.run_context(<step_dir>)`

2. **Edit `src/video_to_essay/main.py`**:
   - Add `--model` to the `essay` subcommand. Doc: applies to essay generation only; style_profile + summarize use their `MODELS` defaults.

3. **Smoke test**: regenerate an essay end-to-end. Length, structure, and section breaks should be similar pre/post.

### Files touched
- `src/video_to_essay/transcriber.py`
- `src/video_to_essay/main.py`

---

## Phase 7 — Migrate `place_images.py` (streaming + JSON + retries)

Most logic-heavy. Last migration before cleanup.

### Steps

1. **Edit `src/video_to_essay/place_images.py`**:
   - Delete `_stream_message` helper (along with its bespoke retry loop)
   - Replace streaming calls with `"".join(llm.stream(task="place_images", messages=..., num_retries=5))`
   - Replace the second non-streaming call with `llm.complete(task="place_images", messages=..., num_retries=5)`
   - Map response shape (text + JSON parsing of the model output remains call-site logic)
   - Add `model` parameter
   - Wrap each top-level entry point in `llm.run_context(<step_dir>)`

2. **Edit `src/video_to_essay/main.py`**:
   - Add `--model` to the `place-images` subcommand

3. **Smoke test**: re-run image placement on an essay with a known frame set. Image positions and figure annotations should be near-identical (some position drift is acceptable; structural breakage is not).

### Files touched
- `src/video_to_essay/place_images.py`
- `src/video_to_essay/main.py`

---

## Phase 8 — Cleanup

Remove direct dependency on `anthropic` and update docs.

### Steps

1. **Verify no remaining direct usage**:
   ```bash
   grep -rn "import anthropic\|from anthropic" src/ tests/
   # Should return zero matches in src/. Tests may still reference it briefly; clean those up too.
   ```

2. **Edit `pyproject.toml`**:
   - Remove `"anthropic>=0.79.0"` from `[project].dependencies`. (It will remain as a transitive dep via litellm.)
   - Run `uv sync` to confirm the lockfile resolves.

3. **Edit `CLAUDE.md`**:
   - Update the "Claude models" section to point at `src/video_to_essay/llm.py:MODELS` as the source of truth for model selection
   - Note the `--model` flag and `llm.run_context` pattern
   - Remove the line "Update all seven files if changing models." — they don't need updating anymore; one dict does it.

4. **Manual end-to-end test**: run a fresh full pipeline on a stable video. Verify all `llm_calls/` directories were populated and the final essay is sane.

### Files touched
- `pyproject.toml`
- `CLAUDE.md`

---

## Sequencing notes

- **Phases 1–4 are independent** of each other and could be re-ordered or batched if desired (each touches a different module).
- **Phase 5 must follow Phase 0** but is otherwise independent.
- **Phases 6 and 7 must follow Phase 0**; they touch the streaming helpers which depend on `llm.stream()` existing.
- **Phase 8 must be last** — premature dep removal would break unmigrated modules.

## Out of scope (tracked in spec §8)

- E2E CI test (separate spec)
- Prompt caching for `scorer.py` and `place_images.py`
- Instructor / Pydantic-validated outputs
- Hosted gateway (Vercel AI Gateway / OpenRouter) routing
- Web app LLM calls
