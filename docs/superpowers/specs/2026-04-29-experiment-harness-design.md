# Experiment Harness — Design

**Date:** 2026-04-29
**Status:** Approved, ready for implementation planning
**Depends on:** `docs/superpowers/specs/2026-04-29-litellm-integration-design.md` (the wrapper at `src/video_to_essay/llm.py` is the harness's only path to the LLM)

## Goal

A test harness that lets one operator A/B test models per pipeline task on cached production runs and view the comparison in the existing runs viewer. Concretely: tune `MODELS` in `llm.py` with real signal — pick a step, pick candidate models, pick a few videos, run, compare quality (via `scorer.py` for essays) and cost (via `litellm.completion_cost`).

Two modes:

- **Single-step**: e.g. `essay` with three candidate models on the same cached transcript. The bread and butter — used to tune one MODELS entry at a time.
- **Full-pipeline (`all`)**: re-run every LLM step end-to-end against named "configs" (partial overrides on top of `MODELS`). Used at the end to validate a tuned dict on a few videos.

## Non-goals

- **Prompt or parameter A/B testing.** v1 varies `model=` only. Same prompts, same kwargs. Prompt sweeps are a follow-up.
- **Re-running non-LLM steps.** `download` and `transcript` aren't varied — they're fetched from cached S3 artifacts. The harness assumes `runs/<video_id>/01_transcript/transcript.txt` exists for any video in `--videos`.
- **Statistical rigor.** With 3–5 videos per sweep, this is "sniff test" tuning, not benchmark science. No confidence intervals, no significance tests.
- **Curated benchmark corpus.** Per the brainstorming, videos come from existing production runs (`runs/`). Operator picks per experiment; no committed test set.
- **UI-initiated sweeps.** CLI is the only kickoff. The viewer is read-only.
- **Inline `--override` ad-hoc configs.** v1.5. v1 names configs in `experiments.yaml`.
- **Diff highlighting in the side-by-side view.** Plain side-by-side with synced scroll only. Diff view is a follow-up.
- **Re-running an existing experiment.** Each invocation creates a new `<exp_id>`. Idempotency is not designed for.

## Architecture

A new module `src/video_to_essay/experiment.py` orchestrates sweeps. It calls existing domain modules (`transcriber`, `place_images`, `scorer`, etc.) which already route through `llm.py` post-litellm-migration, and writes outputs into a parallel `experiments/` tree on S3 (and locally).

```
runs/<video_id>/                         ← canonical, unchanged
  01_transcript/transcript.txt
  02_filter_sponsors/sponsor_segments.json
  03_essay/essay.md
  04_frames/classifications.json
  05_place_images/essay_final.md

experiments/
  <exp_id>/
    manifest.json                        ← config + per-cell summary (single source of truth)
    <video_id>/
      <step>/                            ← e.g. 03_essay or "full"
        <slug>/                          ← model_slug or config name
          output/                        ← step's primary output(s)
          score.json                     ← scorer.py result (essay step only)
          meta.json                      ← model, cost_usd, wall_ms, request_id, status
          llm_calls/*.json               ← raw call logs from llm.py
```

`<exp_id>` format: `<YYYYMMDD-HHMMSS>-<step>-<short_hash>` (e.g. `20260429-153022-essay-a3f9`). Sortable, self-describing, no collisions even for back-to-back invocations. `--label` appends a human-readable suffix.

**Slug format.** `<slug>` for single-step variants is the litellm model string with `/` replaced by `--` (e.g. `anthropic/claude-sonnet-4-5-20250929` → `anthropic--claude-sonnet-4-5-20250929`). For full-pipeline variants, `<slug>` is the config's name verbatim (no transformation needed — names in `experiments.yaml` are already filesystem-safe by convention).

**Local vs S3.** The harness writes to a local working directory at `<repo>/experiments/<exp_id>/...` (override with `--output-base`), then uploads the entire tree to `s3://<bucket>/experiments/<exp_id>/...`. The two layouts are identical. The viewer reads from S3 in production, falls back to the local mirror in dev mode (matching the existing runs viewer behavior).

For full-pipeline experiments, `<step>` is `full` and the variant directory contains a nested `steps/<NN_step_name>/` for each pipeline step:

```
experiments/<exp_id>/<video_id>/full/<config_name>/
  steps/
    02_filter_sponsors/output/, llm_calls/
    03_essay/output/, llm_calls/
    04_frames/output/, llm_calls/
    05_place_images/output/, llm_calls/
  meta.json     (see schema below)
```

**`meta.json` schema (full-pipeline variant):**

```json
{
  "config_name": "cheap-mix",
  "config_resolved": { "essay_single": "openai/gpt-5-mini", "essay_multi": "...", "...": "..." },
  "status": "ok",
  "total_cost_usd": 0.42,
  "total_wall_ms": 87000,
  "per_step": {
    "02_filter_sponsors": { "cost_usd": 0.01, "wall_ms": 3200, "status": "ok" },
    "03_essay":           { "cost_usd": 0.21, "wall_ms": 12400, "status": "ok" },
    "04_frames":          { "cost_usd": 0.07, "wall_ms": 41000, "status": "ok" },
    "05_place_images":    { "cost_usd": 0.13, "wall_ms": 30400, "status": "ok" }
  }
}
```

For single-step variants, `meta.json` is flatter — just `model`, `status`, `cost_usd`, `wall_ms`, `request_id`.

## CLI shape

```
video-to-essay experiment <step> [OPTIONS]

Arguments:
  step  One of: essay, place_images, summarize, sponsor_filter, frame_classify,
        diarize, score, all                                          [required]

Options:
  --videos TEXT          Comma-separated YouTube video IDs (must exist in runs/) [required]
  --models TEXT          Comma-separated litellm model strings (single-step only)
  --configs TEXT         Comma-separated config names from experiments.yaml (--step all only)
  --label TEXT           Human-readable label appended to exp_id
  --concurrency INT      Parallel cells. Default: 4
  --dry-run              Print sweep plan + cost estimate, then exit
  --yes                  Skip the interactive confirm prompt
  --output-base PATH     Local mirror dir for variant files. Default: experiments/
```

**Validation (fail fast, before any LLM call):**

- `step != all` → requires `--models`, rejects `--configs`
- `step == all` → requires `--configs`, rejects `--models`
- Each `--videos` ID gets one S3 head-check; missing inputs error upfront with the exact missing path
- Each `--configs` name must exist in `experiments.yaml`
- Each `--models` string must pass `litellm.utils.get_llm_provider(model)` (catches typos)

**Sample run:**

```
$ video-to-essay experiment essay --videos a,b,c --models anthropic/claude-sonnet-4-5,openai/gpt-5

Sweep plan:
  step=essay, models=[anthropic/claude-sonnet-4-5, openai/gpt-5], videos=[a, b, c]
  → 6 cells, concurrency=4

Estimated cost: $1.20–$1.80
Proceed? [y/N] y

[1/6] a / anthropic/claude-sonnet-4-5  ✓ ok    12s   $0.21   score 8.4
[2/6] a / openai/gpt-5                 ✓ ok    9s    $0.31   score 8.2
[3/6] b / anthropic/claude-sonnet-4-5  ✓ ok    10s   $0.18   score 8.1
[4/6] b / openai/gpt-5                 ✗ failed: RateLimitError (anthropic)
[5/6] c / anthropic/claude-sonnet-4-5  ✓ ok    14s   $0.24   score 8.7
[6/6] c / openai/gpt-5                 ✓ ok    11s   $0.34   score 8.3

Sweep complete: 5/6 ok, 1 failed
exp_id: 20260429-153022-essay-a3f9
View: http://localhost:3000/experiments/20260429-153022-essay-a3f9
```

## Configs (`experiments.yaml`)

Single YAML file at repo root, committed. Each named config is a *partial* dict layered on top of `MODELS` from `llm.py`. Empty config = current production defaults.

```yaml
configs:
  baseline: {}

  cheap-mix:
    essay_single: openai/gpt-5-mini
    frame_classify: google/gemini-2.5-flash

  premium:
    essay_single: anthropic/claude-opus-4-7
    place_images: anthropic/claude-opus-4-7

  gpt5-essay:
    essay_single: openai/gpt-5
    essay_multi: openai/gpt-5
```

The slug used in the storage path is the config's name (e.g. `experiments/<exp_id>/abc123/full/cheap-mix/...`). Renaming or editing `experiments.yaml` after a sweep doesn't lose what was actually run — the manifest snapshots the resolved dict per config at sweep time:

```json
{
  "configs": {
    "cheap-mix": {
      "essay_single": "openai/gpt-5-mini",
      "essay_multi": "anthropic/claude-sonnet-4-5-20250929",
      "frame_classify": "google/gemini-2.5-flash",
      "...": "..."
    }
  }
}
```

## Orchestration (`experiment.py`)

~400 lines. Owns the sweep loop, input fetching, per-cell execution, manifest writing, and cost estimation.

**Per-cell flow:**

```python
def run_cell(exp_id, video_id, step, model_or_config, work_dir):
    # 1. Fetch step inputs from S3 → work_dir (cached per-video across cells)
    fetch_step_inputs(video_id, step, work_dir)

    variant_dir = work_dir / "variant"
    (variant_dir / "llm_calls").mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    try:
        with llm.run_context(variant_dir):
            if step == "all":
                output_paths = run_full_pipeline(
                    video_id, work_dir, variant_dir, config=model_or_config
                )
            else:
                output_paths = run_single_step(
                    step, work_dir, variant_dir, model=model_or_config
                )
        status = "ok"
    except Exception as e:
        status = f"failed: {e!r}"
        output_paths = {}

    wall_ms = int((time.monotonic() - t0) * 1000)
    cost_usd = sum_costs_from_llm_calls(variant_dir / "llm_calls")

    if step == "essay" and status == "ok":
        score_result = scorer.score_essay(
            transcript=read(work_dir / "transcript.txt"),
            essay=read(output_paths["essay"]),
        )
        write_json(variant_dir / "score.json", score_result)

    write_json(variant_dir / "meta.json", {...})
    s3_upload_dir(variant_dir, f"experiments/{exp_id}/{video_id}/{step}/{slug}/")
    return cell_summary
```

**Concurrency.** `concurrent.futures.ThreadPoolExecutor` with `max_workers=4` default. LiteLLM is thread-safe; `llm.run_context` uses `ContextVar`s, which `ThreadPoolExecutor` workers do *not* inherit by default. Each cell's worker function therefore opens its own `llm.run_context(variant_dir)` (matching the pattern in `scorer.py`, where `step_dir` is captured on the calling thread and passed explicitly into each worker). No shared state across cells. Configurable via `--concurrency`. Default is conservative because Anthropic rate limits hit fast on parallel essays.

**Failure handling.** One cell's failure does not abort the sweep. Exception is captured, `meta.json` records `status: "failed: <repr>"`, manifest gets `cell.status: "failed"`. The CLI prints a final summary with the count and which cells failed. The variant directory is still uploaded (with whatever partial output exists, or empty) so the viewer can show the failure inline.

**Input fetching.** `fetch_step_inputs(video_id, step, work_dir)` knows each step's input set:

| Step | Inputs read from `runs/<video_id>/` |
|---|---|
| `essay` | `01_transcript/transcript.txt`, `02_filter_sponsors/sponsor_segments.json`. For multi-speaker transcripts the style profile is recomputed in-memory inside `transcript_to_essay` — it is not persisted to disk in the canonical run, so the harness inherits the same behavior. |
| `place_images` | `03_essay/essay.md`, `04_frames/classifications.json`, `04_frames/kept/*.jpg` |
| `score` | `01_transcript/transcript.txt`, `05_place_images/essay_final.md` |
| `summarize` | `03_essay/essay.md` |
| `sponsor_filter` | `01_transcript/transcript.txt` |
| `frame_classify` | `04_frames/<sampled frames>` |
| `diarize` | `01_transcript/diarization.json` |
| `all` | `01_transcript/transcript.txt`, `01_transcript/diarization.json` (start of LLM portion) |

Pulled from S3 via existing `s3.py` helpers. Cached per-`(video_id, exp_id)` so multi-cell sweeps don't redownload.

**Step output redirection.** Most domain entry points (`transcript_to_essay`, `place_images_in_essay`, `annotate_essay`, `filter_sponsors`, `summarize_essay`, `score_essay`) already return strings or dicts and let the caller decide where to write — the harness simply writes those return values into the variant tree itself, no module change required. The two exceptions are `extract_frames.extract_and_classify` and `diarize.map_speaker_names`, which write artifacts (kept frames, classifications JSON, diarization JSON) to disk directly; both already accept an `output_dir: Path` parameter, so the harness just passes the variant dir there. No domain-module signatures need to change for v1.

**Full-pipeline orchestrator.** `run_full_pipeline` chains step outputs:

```
filter_sponsors(transcript) → sponsor_segments (variant_dir/steps/02_filter_sponsors/output/)
essay(transcript, sponsor_segments) → essay.md (variant_dir/steps/03_essay/output/)
extract_frames(video_path, transcript) → classifications + kept frames (variant_dir/steps/04_frames/...)
place_images(essay.md, classifications) → essay_final.md (variant_dir/steps/05_place_images/output/)
```

Each step reads from the variant tree (or from canonical `runs/` for inputs that aren't varied — like `transcript.txt`). The `MODELS` override for the cell's config flows through `model=` parameters per step.

**Cost estimation (dry-run).** Reads each candidate video's canonical `llm_calls/*.json` for token counts, then for each candidate model:

```python
prompt_cost, completion_cost = litellm.cost_per_token(
    model=candidate_model,
    prompt_tokens=canonical_input_tokens,
    completion_tokens=canonical_output_tokens,
)
```

Sum across cells, report min/max bracket. Warns if any candidate model has no pricing data (returns `None`).

## `llm.py` extensions

Three new fields in the persisted JSON: `cost_usd`, `wall_ms`. The `_persist` function captures call start time and computes cost via `litellm.completion_cost`:

```python
def _safe_completion_cost(response) -> float | None:
    try:
        return litellm.completion_cost(completion_response=response)
    except Exception:
        return None
```

`complete()` and `stream()` each grab a `time.monotonic()` snapshot before invoking `litellm.completion`. For `stream()`, `wall_ms` covers the entire stream-drain loop (matching real wait time).

Cost can be `None` for self-hosted models or models with stale pricing data. `sum_costs_from_llm_calls` returns `None` if any call lacks pricing — better to surface "unknown total" than silently understate.

## Scorer integration

Scorer runs **only** on the `essay` step. Other steps are eyeballed in the viewer.

| Step | Auto-scored? |
|---|---|
| `essay` | yes |
| everything else (`place_images`, `summarize`, `sponsor_filter`, `frame_classify`, `diarize`, `score`, `all`) | no |

For `all` (full-pipeline) experiments, follow up with a separate `--step score` experiment against the candidate's `essay_final.md` if you want a number.

**Ground truth.** Scorer compares an essay against its source transcript. The transcript is always the canonical `runs/<video_id>/01_transcript/transcript.txt` regardless of which model produced the variant essay.

**Scorer model.** Uses `MODELS["score"]` — not overridden by the experiment. Scorer must be a stable judge across all variants in a sweep. The manifest snapshots `MODELS["score"]` at sweep time so cross-experiment comparisons can detect when the judge changed.

**Scorer's own LLM calls** persist into the variant's `llm_calls/` (the cell is wrapped in `llm.run_context(variant_dir)`). Tagged with `task: "score"`, separable from the candidate's calls (`task: "essay_single"` etc.). The variant's total `cost_usd` correctly includes scorer cost — scorer cost is part of experiment cost.

**Scorer failure.** If scorer fails on a variant (rate limit, parse error), the cell's `meta.json` records `score_status: "failed"` and `score.json` is omitted. The variant is still surfaced in the viewer with outputs visible — only the score is missing. Cell `status` stays `ok` (the step itself succeeded).

## Viewer extensions

Two surfaces in the existing Next.js app: a new top-level `/experiments` route and a small cross-link on `/runs/<videoId>`.

### `/experiments` (list view)

Server component. On each page load:

1. `ListObjectsV2` with `Prefix=experiments/` and `Delimiter=/` returns the set of `<exp_id>` directory names — one S3 round trip, no pagination at expected sizes (one operator, single-digit experiments per week, ~250 after a year, well under the 1000-entry single-call limit).
2. Parallel `GetObject` for each `<exp_id>/manifest.json` — small files (~1–5 KB each), Promise.all from the server component.
3. Render the table.

Manifest is the single source of truth — no denormalized index file. If list-view latency ever becomes noticeable (it shouldn't at this scale), wrap the read function in Next.js `cache()` for in-process memoization rather than introducing a new on-disk artifact.

```
Experiments

When               Step       Configs/Models                      Videos    Status
─────────────────────────────────────────────────────────────────────────────────
2d ago             essay      sonnet-4-5, gpt-5, gemini-2.5      3         12/12 ok
3d ago             all        baseline, cheap-mix                2         3/4 ok (1 failed)
```

Reading one indexed file avoids a `ListObjectsV2` walk on every page load.

### `/experiments/<exp_id>` (detail view)

Server component fetches `manifest.json` + per-cell `meta.json` and `score.json` files in parallel. Top of page shows the manifest summary; aggregate table per (model/config × video) cell:

```
                         abc123          def456          ghi789      avg
─────────────────────────────────────────────────────────────────────────
sonnet-4-5    score       8.4             8.1             8.7         8.4
              cost        $0.21           $0.18           $0.24       $0.21
              wall        12s             10s             14s
gpt-5         score       8.2             8.5             8.3         8.3
              cost        $0.31           $0.26           $0.34       $0.30
              wall        9s              8s              11s
```

Score column color-coded: green if score ≥ best - 0.3, red if score < best - 1.0, otherwise stone.

For experiments where scoring didn't run (i.e. anything other than `--step essay`), the score column is omitted and the table ranks visually by cost ascending. Operators eyeball the side-by-side for quality.

Click any cell → side-by-side at `/experiments/<exp_id>/<video_id>`.

### `/experiments/<exp_id>/<video_id>` (side-by-side)

Markdown panels for each variant, rendered with the existing `markdown.ts` from the runs viewer. Synchronized vertical scroll. Header strip per panel: model/config, score, cost, wall_ms, expandable "show llm calls" section showing the variant's `llm_calls/*.json` (collapsed by default).

For full-pipeline experiments, a step selector at top (`02_filter_sponsors | 03_essay | 04_frames | 05_place_images`) flips which step's output the panels show.

### Cross-link from `/runs/<videoId>`

Small sidebar populated server-side from the same ListObjectsV2 + parallel manifest reads as the `/experiments` list view, then filtered to manifests whose `videos` array contains the current `videoId`. Reuses the same fetch helper; no new infrastructure. Lazy: if no manifests match, the sidebar isn't rendered.

```
Appears in experiments
─────────────
2d ago · essay (sonnet vs gpt-5 vs gemini-2.5)
3d ago · all (baseline vs cheap-mix)
```

Lazy: only rendered if the index has entries for this video.

### File layout

```
web/app/
  experiments/
    layout.tsx                      ← reuses admin auth gate
    page.tsx                        ← list view
    [expId]/
      page.tsx                      ← summary + aggregate table
      [videoId]/
        page.tsx                    ← side-by-side variant compare
        SideBySide.tsx              ← client component, synced scroll
  api/
    experiments/
      [expId]/
        files/route.ts              ← lazy file fetch (mirrors /api/runs/.../files)
  lib/
    admin.ts                        ← extracted shared admin auth gate
```

The existing `web/app/runs/layout.tsx` is updated to import from `lib/admin.ts`. Same gate, same hardcoded email, no behavior change.

## Testing strategy

| Layer | Coverage |
|---|---|
| `experiment.py` orchestration | Unit tests with mocked `llm.complete` and mocked S3: cell success, cell failure surfaced in manifest, dry-run cost math, input-fetch missing-video error, manifest writing, multi-cell concurrency (verify cells run, not race conditions) |
| `experiments.yaml` loading | Unit test: missing config name, malformed YAML, partial config merging onto `MODELS` defaults |
| Step input fetching | Unit test: `fetch_step_inputs("essay", ...)` requests the right S3 keys per step |
| Scorer integration | Reuse the existing `tests/test_scorer.py` mock pattern; verify `score.json` lands in variant dir |
| Viewer | Manual verification only (matches the runs viewer's testing posture) |
| End-to-end smoke | `video-to-essay experiment essay --videos <stable_id> --models anthropic/claude-haiku-4-5,anthropic/claude-haiku-4-5 --yes` — same model twice, cheapest possible, verifies harness shape end-to-end without a real comparison signal |

Tests use a `tmp_path` fixture YAML for `experiments.yaml`; no CI dependency on the committed file.

## Sequencing

All phases of the litellm migration in `2026-04-29-litellm-integration-design.md` are complete (through commit `1004e5c`, "Phase 8: Drop anthropic direct dep"). The harness work is fully unblocked — single-step and full-pipeline experiments can both be implemented in one pass.

## File touchlist

| File | Change |
|---|---|
| `src/video_to_essay/experiment.py` | new (~400 lines) |
| `src/video_to_essay/llm.py` | extend `_persist` with `cost_usd`, `wall_ms` |
| `src/video_to_essay/main.py` | add `experiment` Typer command |
| `experiments.yaml` | new at repo root, committed (with `baseline: {}` and example configs) |
| `web/app/experiments/...` | new (per Viewer Extensions section) |
| `web/app/runs/[videoId]/page.tsx` | add "Appears in experiments" sidebar |
| `web/app/lib/admin.ts` | extracted shared admin gate |
| `tests/test_experiment.py` | new |
| `tests/test_llm.py` | extend for `cost_usd` / `wall_ms` |

## Out of scope (follow-ups)

- **Inline `--override` on top of a named config** (v1.5)
- **Diff highlighting** in the side-by-side view
- **Charts** (cost vs score scatter for sweeps with > 3 candidates)
- **Filter / search** on the `/experiments` list
- **Re-running an existing experiment** (idempotency, partial re-runs of failed cells)
- **Prompt or parameter A/B testing** (varying anything beyond `model=`)
- **Statistical analysis** (confidence intervals, significance tests, per-dimension t-tests across models)
- **Curated benchmark corpus** committed to the repo
- **Harness for the `score` task itself** (calibrating the judge model — would need a separate ground-truth dataset)

## Validation TODO

- [x] Single-step (`--step essay`) sweep against `adfezGXZMTQ`: Sonnet 4.5 vs Kimi K2 0905 — both cells succeeded, viewer renders aggregate table, per-dimension scores, side-by-side panels with score breakdown + meta + llm_calls accordions.
- [ ] **Full-pipeline (`--step all`) sweep end-to-end** — exercises `_run_full_pipeline` (sponsor_filter → essay → frame_classify → place_images), the `experiments.yaml` config-resolution path, and the `/experiments/<expId>/<videoId>?step=…` step-selector in the viewer. Suggested run:
  ```bash
  # In experiments.yaml, add a partial config that swaps text tasks only and
  # leaves vision tasks (frame_classify, place_images) on the canonical defaults.
  configs:
    kimi-essays-only:
      essay_single: openrouter/moonshotai/kimi-k2-0905
      essay_multi:  openrouter/moonshotai/kimi-k2-0905
      sponsor_filter: openrouter/moonshotai/kimi-k2-0905
      summarize:    openrouter/moonshotai/kimi-k2-0905
  # Then:
  video-to-essay experiment all --videos adfezGXZMTQ \
      --configs baseline,kimi-essays-only --no-upload --yes
  ```
  Verify: per-cell `steps/02_filter_sponsors/`, `steps/03_essay/`, `steps/04_frames/`, `steps/05_place_images/` all populate; the viewer's step selector flips between them; `meta.json` includes the `per_step` cost/wall breakdown described in the schema above.
- [ ] **S3 upload path** — every smoke test so far has used `--no-upload`. Drop the flag once and confirm `experiments/<exp_id>/...` lands in the bucket and the viewer fetches via S3 (not local fallback).
- [ ] **Re-run scorer with a different judge model** (`--step score`) to demonstrate the calibration use case for the judge itself — orthogonal to the candidate sweeps.

## Open risks

- **Pricing data lag.** `litellm.completion_cost` is accurate for major providers but lags by hours/days for newly released models. v1 surfaces `cost_usd: null` rather than guessing — operator notices the gap and reruns or backfills after a `litellm` bump.
- **Scorer judgments are noisy on stochastic outputs.** A score difference of 0.3 between two models is within noise; differences > 1.0 are signal. The viewer's color-coding reflects this (red below best - 1.0). Two videos per sweep is borderline; 3+ is recommended for any meaningful comparison.
- **Anthropic rate limits** on parallel essay generation. Default `--concurrency=4` is conservative; sweeps of size > 10 may need `--concurrency=2` to avoid `RateLimitError`. The `num_retries=5` already configured at call sites should absorb most transient hits.
- **Domain modules largely don't need changes.** Most entry points already return strings/dicts and let the caller pick a destination, and the two that write artifacts directly (`extract_frames.extract_and_classify`, `diarize.map_speaker_names`) already accept `output_dir: Path`. The orchestrator can write into the variant tree itself, so this risk has narrowed to "make sure the variant dir is threaded through to the two write-to-disk callers" — a one-line concern, not a multi-module sweep.
