"""
Experiment harness — A/B test models per pipeline task on cached production runs.

Two modes:
- Single-step: vary the model on one step (e.g. essay) across N candidate models
- Full-pipeline (`all`): re-run every LLM step end-to-end with named "configs"
  (partial overrides on top of MODELS).

Outputs land in a parallel `experiments/` tree on S3 (and locally).

See docs/superpowers/specs/2026-04-29-experiment-harness-design.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from video_to_essay import llm, s3
from video_to_essay.diarize import map_speaker_names
from video_to_essay.extract_frames import extract_and_classify, parse_transcript
from video_to_essay.filter_sponsors import filter_sponsors as run_filter_sponsors
from video_to_essay.place_images import (
    annotate_essay,
    load_kept_frames,
    place_images_in_essay,
)
from video_to_essay.scorer import score_essay
from video_to_essay.summarize import summarize_essay
from video_to_essay.transcriber import transcript_to_essay

logger = logging.getLogger(__name__)


SINGLE_STEPS = {
    "essay",
    "place_images",
    "summarize",
    "sponsor_filter",
    "frame_classify",
    "diarize",
    "score",
}
ALL_STEPS = SINGLE_STEPS | {"all"}

DEFAULT_OUTPUT_BASE = Path("experiments")
DEFAULT_RUNS_BASE = Path("runs")

# S3 layout
S3_RUNS_PREFIX = "runs"
S3_EXPERIMENTS_PREFIX = "experiments"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

@dataclass
class ExperimentConfigs:
    """Parsed experiments.yaml — partial MODELS overrides keyed by config name."""

    configs: dict[str, dict[str, str]]

    def resolve(self, name: str) -> dict[str, str]:
        """Return the full MODELS dict with this config's overrides applied."""
        if name not in self.configs:
            raise KeyError(f"unknown config '{name}'")
        merged = dict(llm.MODELS)
        merged.update(self.configs[name])
        return merged


def load_configs(path: Path) -> ExperimentConfigs:
    """Load experiments.yaml. Raises FileNotFoundError or ValueError on bad input."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    raw = yaml.safe_load(path.read_text()) or {}
    configs = raw.get("configs", {})
    if not isinstance(configs, dict):
        raise ValueError(f"{path}: 'configs' must be a mapping")

    # Each config value must itself be a mapping (possibly empty)
    cleaned: dict[str, dict[str, str]] = {}
    for name, override in configs.items():
        if override is None:
            cleaned[name] = {}
        elif isinstance(override, dict):
            cleaned[name] = {str(k): str(v) for k, v in override.items()}
        else:
            raise ValueError(f"{path}: config '{name}' must be a mapping")

    return ExperimentConfigs(configs=cleaned)


# ---------------------------------------------------------------------------
# IDs and slugs
# ---------------------------------------------------------------------------

def make_exp_id(step: str, label: str | None = None) -> str:
    """`<YYYYMMDD-HHMMSS>-<step>-<short_hash>[-<label>]`."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short = secrets.token_hex(2)
    base = f"{ts}-{step}-{short}"
    if label:
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        return f"{base}-{safe}"
    return base


def slug_for_model(model: str) -> str:
    """Filesystem-safe slug for a litellm model string."""
    return model.replace("/", "--")


# ---------------------------------------------------------------------------
# Cell types
# ---------------------------------------------------------------------------

@dataclass
class CellPlan:
    video_id: str
    step: str
    variant: str          # model string (single-step) or config name (all)
    slug: str             # variant key in storage path

    @property
    def cell_id(self) -> str:
        return f"{self.video_id}/{self.step}/{self.slug}"


@dataclass
class CellResult:
    plan: CellPlan
    status: str           # "ok" or "failed: <repr>"
    cost_usd: float | None
    wall_ms: int
    score_overall: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Input fetching
# ---------------------------------------------------------------------------

# Per-step input files relative to runs/<video_id>/
_STEP_INPUTS: dict[str, list[str]] = {
    "essay": [
        "01_transcript/transcript.txt",
        "02_filter_sponsors/transcript_clean.txt",
    ],
    "place_images": [
        "03_essay/essay.md",
        "04_frames/classifications.json",
    ],
    "score": [
        "01_transcript/transcript.txt",
        "05_place_images/essay_final.md",
    ],
    "summarize": ["03_essay/essay.md"],
    "sponsor_filter": ["01_transcript/transcript.txt"],
    "frame_classify": [],  # video file + transcript; resolved at cell time
    "diarize": ["01_transcript/diarization.json"],
    "all": [
        "01_transcript/transcript.txt",
        "01_transcript/diarization.json",
    ],
}


def _local_run_path(video_id: str, rel: str, runs_base: Path) -> Path:
    return runs_base / video_id / rel


def fetch_step_inputs(
    video_id: str,
    step: str,
    work_dir: Path,
    runs_base: Path = DEFAULT_RUNS_BASE,
) -> dict[str, Path]:
    """Ensure each input for the step is present locally; return path map.

    Prefers an existing local copy (under runs_base) and falls back to S3.
    Caches by (video_id, work_dir) — work_dir already namespaces by exp_id.
    """
    inputs = _STEP_INPUTS.get(step, [])
    cache_dir = work_dir / "inputs" / video_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    out: dict[str, Path] = {}
    for rel in inputs:
        local = _local_run_path(video_id, rel, runs_base)
        target = cache_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if local.exists():
            target.write_bytes(local.read_bytes())
        else:
            try:
                data = s3.download_file(video_id, rel)
            except Exception as e:
                raise FileNotFoundError(
                    f"missing input for video {video_id}: {rel} (local and S3): {e}"
                ) from e
            target.write_bytes(data)
        out[rel] = target

    # Frame classify needs video + transcript; place_images needs kept frames.
    if step == "frame_classify":
        for rel in ("00_download/video.mp4", "01_transcript/transcript.txt"):
            local = _local_run_path(video_id, rel, runs_base)
            if local.exists():
                target = cache_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(local.read_bytes())
                out[rel] = target

    return out


# ---------------------------------------------------------------------------
# Cell execution — single step
# ---------------------------------------------------------------------------

def _run_single_step(
    step: str,
    video_id: str,
    inputs: dict[str, Path],
    variant_dir: Path,
    runs_base: Path,
    model: str,
) -> dict[str, Path]:
    """Execute one single-step variant. Returns paths of primary outputs."""
    out_dir = variant_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    if step == "essay":
        # Match the canonical pipeline: feed the sponsor-filtered transcript.
        transcript = inputs["02_filter_sponsors/transcript_clean.txt"].read_text()
        text = transcript_to_essay(transcript, video_id=video_id, model=model)
        out_path = out_dir / "essay.md"
        out_path.write_text(text)
        return {"essay": out_path}

    if step == "sponsor_filter":
        transcript = inputs["01_transcript/transcript.txt"].read_text()
        cleaned, ranges = run_filter_sponsors(transcript, model=model)
        clean_path = out_dir / "transcript_clean.txt"
        seg_path = out_dir / "sponsor_segments.json"
        clean_path.write_text(cleaned)
        seg_path.write_text(json.dumps(ranges, indent=2))
        return {"transcript_clean": clean_path, "sponsor_segments": seg_path}

    if step == "summarize":
        # summarize_essay rewrites the file in place
        src = inputs["03_essay/essay.md"]
        dst = out_dir / "essay.md"
        dst.write_text(src.read_text())
        summarize_essay(dst, force=True, model=model)
        return {"essay": dst}

    if step == "place_images":
        essay_text = inputs["03_essay/essay.md"].read_text()
        classifications = inputs["04_frames/classifications.json"]
        # Pull kept/ frames from S3 or local
        kept_local = runs_base / video_id / "04_frames" / "kept"
        if not kept_local.exists():
            s3.download_run(video_id, step_dirs=["04_frames"])
        kept = load_kept_frames(classifications, kept_local)
        if not kept:
            placed = essay_text
        else:
            placed = place_images_in_essay(
                essay_text, kept, image_prefix="../04_frames/kept/", model=model,
            )
        annotated = annotate_essay(placed, model=model)
        placed_path = out_dir / "essay_with_images.md"
        final_path = out_dir / "essay_final.md"
        placed_path.write_text(placed)
        final_path.write_text(annotated)
        return {"essay_with_images": placed_path, "essay_final": final_path}

    if step == "frame_classify":
        video_path = inputs.get("00_download/video.mp4")
        transcript_path = inputs.get("01_transcript/transcript.txt")
        if video_path is None or transcript_path is None:
            raise FileNotFoundError(
                f"frame_classify requires local video + transcript for {video_id}"
            )
        transcript_entries = parse_transcript(transcript_path.read_text())
        extract_and_classify(
            video=video_path,
            output_dir=out_dir,
            transcript_entries=transcript_entries,
            model=model,
        )
        return {"classifications": out_dir / "classifications.json"}

    if step == "diarize":
        # The diarization step needs a metadata blob and video downloaded;
        # this branch only re-runs the speaker name mapping (LLM portion).
        seg_path = inputs["01_transcript/diarization.json"]
        segments = json.loads(seg_path.read_text())
        metadata_path = runs_base / video_id / "00_download" / "metadata.json"
        metadata = (
            json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        )
        mapping = map_speaker_names(segments, metadata, out_dir, model=model)
        out_path = out_dir / "speaker_map.json"
        out_path.write_text(json.dumps(mapping, indent=2))
        return {"speaker_map": out_path}

    if step == "score":
        # `score` as a sweep step exists to A/B test the *judge* model itself.
        # The candidate essay is fixed (the canonical run output).
        transcript = inputs["01_transcript/transcript.txt"].read_text()
        essay = inputs["05_place_images/essay_final.md"].read_text()
        result = score_essay(transcript, essay, model=model)
        out_path = out_dir / "score.json"
        out_path.write_text(json.dumps(result, indent=2))
        return {"score": out_path}

    raise ValueError(f"unknown step: {step}")


def _run_full_pipeline(
    video_id: str,
    inputs: dict[str, Path],
    variant_dir: Path,
    runs_base: Path,
    resolved_models: dict[str, str],
) -> dict[str, Path]:
    """Run filter_sponsors -> essay -> frames -> place_images, threading per-step
    overrides from `resolved_models`. Steps write into variant_dir/steps/.

    Returns a flat path map for the manifest.
    """
    steps_root = variant_dir / "steps"
    steps_root.mkdir(parents=True, exist_ok=True)

    # 02 filter_sponsors
    fs_dir = steps_root / "02_filter_sponsors" / "output"
    fs_dir.mkdir(parents=True, exist_ok=True)
    transcript_text = inputs["01_transcript/transcript.txt"].read_text()
    with llm.run_context(steps_root / "02_filter_sponsors"):
        cleaned, sponsor_ranges = run_filter_sponsors(
            transcript_text, model=resolved_models["sponsor_filter"],
        )
    (fs_dir / "transcript_clean.txt").write_text(cleaned)
    (fs_dir / "sponsor_segments.json").write_text(json.dumps(sponsor_ranges, indent=2))

    # 03 essay
    essay_dir = steps_root / "03_essay" / "output"
    essay_dir.mkdir(parents=True, exist_ok=True)
    with llm.run_context(steps_root / "03_essay"):
        essay_text = transcript_to_essay(
            cleaned, video_id=video_id, model=resolved_models["essay_single"],
        )
    essay_path = essay_dir / "essay.md"
    essay_path.write_text(essay_text)

    # 04 frame_classify (requires the canonical video + transcript)
    frames_dir = steps_root / "04_frames" / "output"
    frames_dir.mkdir(parents=True, exist_ok=True)
    video_local = runs_base / video_id / "00_download" / "video.mp4"
    if video_local.exists():
        transcript_entries = parse_transcript(transcript_text)
        with llm.run_context(steps_root / "04_frames"):
            extract_and_classify(
                video=video_local,
                output_dir=frames_dir,
                transcript_entries=transcript_entries,
                sponsor_ranges=sponsor_ranges,
                model=resolved_models["frame_classify"],
            )
    else:
        logger.warning(
            "video file missing for %s; skipping frame_classify in full-pipeline",
            video_id,
        )

    # 05 place_images
    place_dir = steps_root / "05_place_images" / "output"
    place_dir.mkdir(parents=True, exist_ok=True)
    classifications_path = frames_dir / "classifications.json"
    kept_local = frames_dir / "kept"
    final_path = place_dir / "essay_final.md"
    if classifications_path.exists() and kept_local.exists():
        kept = load_kept_frames(classifications_path, kept_local)
        with llm.run_context(steps_root / "05_place_images"):
            placed = place_images_in_essay(
                essay_text, kept, image_prefix="../04_frames/kept/",
                model=resolved_models["place_images"],
            )
            annotated = annotate_essay(placed, model=resolved_models["place_images"])
        (place_dir / "essay_with_images.md").write_text(placed)
        final_path.write_text(annotated)
    else:
        # No frames available; final == essay
        final_path.write_text(essay_text)

    return {
        "transcript_clean": fs_dir / "transcript_clean.txt",
        "sponsor_segments": fs_dir / "sponsor_segments.json",
        "essay": essay_path,
        "essay_final": final_path,
    }


# ---------------------------------------------------------------------------
# Cost summing
# ---------------------------------------------------------------------------

def sum_costs_from_llm_calls(*dirs: Path) -> tuple[float | None, dict[str, float]]:
    """Walk llm_calls/*.json under each dir; return (total, per_task).

    Total is None if any call is missing cost_usd (better to surface "unknown"
    than silently understate).
    """
    total = 0.0
    per_task: dict[str, float] = {}
    saw_unknown = False

    for root in dirs:
        if not root.exists():
            continue
        for call_file in root.rglob("llm_calls/*.json"):
            try:
                payload = json.loads(call_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            cost = payload.get("cost_usd")
            task = payload.get("task", "unknown")
            if cost is None:
                saw_unknown = True
                continue
            total += float(cost)
            per_task[task] = per_task.get(task, 0.0) + float(cost)

    return (None if saw_unknown else round(total, 6)), per_task


def estimate_cell_cost(video_id: str, step: str, candidate_model: str, runs_base: Path) -> tuple[float | None, float | None]:
    """Best-effort cost bracket using the canonical run's token counts.

    Returns (low, high) — both None if we can't estimate.
    """
    canonical_dir = runs_base / video_id
    if not canonical_dir.exists():
        return (None, None)

    # Use prompt/completion tokens recorded for matching task entries
    # (e.g. "essay_single" / "essay_multi" for step "essay").
    matchers = {
        "essay": {"essay_single", "essay_multi", "style_profile"},
        "sponsor_filter": {"sponsor_filter"},
        "place_images": {"place_images"},
        "summarize": {"summarize"},
        "frame_classify": {"frame_classify"},
        "diarize": {"diarize_helper"},
        "score": {"score"},
        "all": None,  # any
    }
    wanted = matchers.get(step)

    try:
        import litellm as _ll
    except ImportError:  # pragma: no cover
        return (None, None)

    total_in = total_out = 0
    for call_file in canonical_dir.rglob("llm_calls/*.json"):
        try:
            payload = json.loads(call_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if wanted is not None and payload.get("task") not in wanted:
            continue
        total_in += int(payload.get("input_tokens") or 0)
        total_out += int(payload.get("output_tokens") or 0)

    if total_in == 0 and total_out == 0:
        return (None, None)

    try:
        prompt_cost, completion_cost = _ll.cost_per_token(
            model=candidate_model,
            prompt_tokens=total_in,
            completion_tokens=total_out,
        )
        if prompt_cost is None or completion_cost is None:
            return (None, None)
        cost = float(prompt_cost) + float(completion_cost)
        # Crude bracket: ±20% to reflect variance vs. canonical run
        return (round(cost * 0.8, 4), round(cost * 1.2, 4))
    except Exception:
        return (None, None)


# ---------------------------------------------------------------------------
# Per-cell execution
# ---------------------------------------------------------------------------

def run_cell(
    plan: CellPlan,
    exp_id: str,
    work_root: Path,
    runs_base: Path,
    configs: ExperimentConfigs | None,
    upload: bool,
) -> CellResult:
    """Run a single experiment cell and write its variant directory.

    Captures errors into the result; does not propagate (so one bad cell
    does not kill the sweep).
    """
    cell_dir = work_root / plan.video_id / plan.step / plan.slug
    variant_dir = cell_dir
    (variant_dir / "llm_calls").mkdir(parents=True, exist_ok=True)

    fetched: dict[str, Path] = {}
    output_paths: dict[str, Path] = {}
    score_overall: float | None = None
    score_status: str | None = None

    t0 = time.monotonic()
    status = "ok"
    try:
        fetched = fetch_step_inputs(
            plan.video_id, plan.step, variant_dir, runs_base=runs_base,
        )
        # NOTE: ContextVar does not propagate into ThreadPoolExecutor workers,
        # so each cell opens its own run_context here (mirrors scorer.py).
        with llm.run_context(variant_dir):
            if plan.step == "all":
                if configs is None:
                    raise ValueError("full-pipeline cell requires configs")
                resolved = configs.resolve(plan.variant)
                output_paths = _run_full_pipeline(
                    plan.video_id, fetched, variant_dir, runs_base, resolved,
                )
            else:
                output_paths = _run_single_step(
                    plan.step, plan.video_id, fetched, variant_dir,
                    runs_base, plan.variant,
                )

            # Score essays automatically (the spec's auto-score rule)
            if plan.step == "essay":
                try:
                    transcript = fetched["01_transcript/transcript.txt"].read_text()
                    essay = output_paths["essay"].read_text()
                    score_result = score_essay(transcript, essay)
                    (variant_dir / "score.json").write_text(
                        json.dumps(score_result, indent=2)
                    )
                    score_overall = float(score_result["overall_score"])
                except Exception as e:
                    score_status = f"failed: {e!r}"
    except Exception as e:
        status = f"failed: {e!r}"
        logger.exception("cell %s failed", plan.cell_id)

    wall_ms = int((time.monotonic() - t0) * 1000)
    cost_usd, per_task = sum_costs_from_llm_calls(variant_dir)

    meta: dict[str, Any] = {
        "step": plan.step,
        "video_id": plan.video_id,
        "variant": plan.variant,
        "slug": plan.slug,
        "status": status,
        "cost_usd": cost_usd,
        "cost_by_task": per_task,
        "wall_ms": wall_ms,
        "outputs": {k: str(v.relative_to(variant_dir)) for k, v in output_paths.items()},
    }
    if plan.step == "all" and configs is not None:
        meta["config_resolved"] = configs.resolve(plan.variant)
    else:
        meta["model"] = plan.variant

    if plan.step == "essay":
        meta["score_status"] = score_status or ("ok" if score_overall is not None else "skipped")
        meta["score_overall"] = score_overall
        meta["judge_model"] = llm.MODELS["score"]

    (variant_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))

    if upload:
        try:
            _upload_variant(exp_id, plan, variant_dir)
        except Exception as e:
            logger.warning("upload failed for %s: %s", plan.cell_id, e)

    return CellResult(
        plan=plan,
        status=status,
        cost_usd=cost_usd,
        wall_ms=wall_ms,
        score_overall=score_overall,
    )


def _upload_variant(exp_id: str, plan: CellPlan, variant_dir: Path) -> None:
    client = s3.get_s3_client()
    bucket, _ = s3._get_config()
    base_prefix = f"{S3_EXPERIMENTS_PREFIX}/{exp_id}/{plan.video_id}/{plan.step}/{plan.slug}"
    for file_path in variant_dir.rglob("*"):
        if not file_path.is_file():
            continue
        key = f"{base_prefix}/{file_path.relative_to(variant_dir)}"
        ct = "application/octet-stream"
        if file_path.suffix == ".json":
            ct = "application/json"
        elif file_path.suffix == ".md":
            ct = "text/markdown; charset=utf-8"
        elif file_path.suffix == ".txt":
            ct = "text/plain; charset=utf-8"
        elif file_path.suffix in {".jpg", ".jpeg"}:
            ct = "image/jpeg"
        client.upload_file(
            str(file_path), bucket, key, ExtraArgs={"ContentType": ct},
        )


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------

@dataclass
class SweepPlan:
    exp_id: str
    step: str
    videos: list[str]
    variants: list[str]   # model strings (single-step) or config names (all)
    cells: list[CellPlan]
    configs: ExperimentConfigs | None


def build_sweep(
    step: str,
    videos: list[str],
    *,
    models: list[str] | None = None,
    config_names: list[str] | None = None,
    label: str | None = None,
    configs: ExperimentConfigs | None = None,
) -> SweepPlan:
    """Validate inputs and produce the cartesian sweep plan."""
    if step not in ALL_STEPS:
        raise ValueError(f"unknown step: {step}")

    if step == "all":
        if not config_names:
            raise ValueError("--step all requires --configs")
        if models:
            raise ValueError("--step all rejects --models (use configs)")
        if configs is None:
            raise ValueError("configs argument required for --step all")
        for name in config_names:
            if name not in configs.configs:
                raise ValueError(f"unknown config '{name}'")
        variants = list(config_names)
        slugs = list(config_names)
    else:
        if not models:
            raise ValueError(f"--step {step} requires --models")
        if config_names:
            raise ValueError(f"--step {step} rejects --configs (use models)")
        _validate_models(models)
        variants = list(models)
        slugs = [slug_for_model(m) for m in models]

    cells = [
        CellPlan(video_id=v, step=step, variant=variant, slug=slug)
        for v in videos
        for variant, slug in zip(variants, slugs, strict=True)
    ]

    exp_id = make_exp_id(step, label)
    return SweepPlan(
        exp_id=exp_id,
        step=step,
        videos=list(videos),
        variants=variants,
        cells=cells,
        configs=configs if step == "all" else None,
    )


def _validate_models(models: list[str]) -> None:
    """Reject typos by asking litellm to identify the provider for each."""
    try:
        from litellm.utils import get_llm_provider
    except ImportError:  # pragma: no cover
        return
    for m in models:
        try:
            get_llm_provider(m)
        except Exception as e:
            raise ValueError(f"invalid model string '{m}': {e}") from e


def verify_video_inputs(
    videos: list[str], step: str, runs_base: Path = DEFAULT_RUNS_BASE
) -> list[str]:
    """Return a list of human-readable errors for missing inputs.

    Empty list = all videos satisfy the step's input requirements (locally
    or on S3).
    """
    errors: list[str] = []
    inputs = _STEP_INPUTS.get(step, [])
    for video_id in videos:
        for rel in inputs:
            local = runs_base / video_id / rel
            if local.exists():
                continue
            try:
                # Cheap S3 head — call download_file with a tiny range trick is
                # noisy; instead just attempt and rely on the per-cell catch.
                # Here we do a real (small) get since most artifacts are small.
                s3.download_file(video_id, rel)
            except Exception as e:
                errors.append(f"{video_id}: missing {rel} ({e})")
                break
    return errors


def run_sweep(
    plan: SweepPlan,
    *,
    concurrency: int = 4,
    runs_base: Path = DEFAULT_RUNS_BASE,
    output_base: Path = DEFAULT_OUTPUT_BASE,
    upload: bool = True,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Execute the sweep. Returns the manifest dict."""
    work_root = output_base / plan.exp_id
    work_root.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[CellResult] = []

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(
                run_cell, cell, plan.exp_id, work_root, runs_base, plan.configs, upload,
            ): cell
            for cell in plan.cells
        }
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            if progress_cb:
                progress_cb(i, len(plan.cells), result)

    finished_at = datetime.now(timezone.utc).isoformat()

    manifest = _build_manifest(plan, results, started_at, finished_at)
    manifest_path = work_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    if upload:
        try:
            client = s3.get_s3_client()
            bucket, _ = s3._get_config()
            client.upload_file(
                str(manifest_path),
                bucket,
                f"{S3_EXPERIMENTS_PREFIX}/{plan.exp_id}/manifest.json",
                ExtraArgs={"ContentType": "application/json"},
            )
        except Exception as e:
            logger.warning("manifest upload failed: %s", e)

    return manifest


def _build_manifest(
    plan: SweepPlan,
    results: list[CellResult],
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    cells_payload: list[dict[str, Any]] = []
    for r in results:
        cells_payload.append({
            "video_id": r.plan.video_id,
            "variant": r.plan.variant,
            "slug": r.plan.slug,
            "status": r.status,
            "cost_usd": r.cost_usd,
            "wall_ms": r.wall_ms,
            "score_overall": r.score_overall,
        })

    manifest: dict[str, Any] = {
        "exp_id": plan.exp_id,
        "step": plan.step,
        "videos": plan.videos,
        "variants": plan.variants,
        "started_at": started_at,
        "finished_at": finished_at,
        "judge_model": llm.MODELS["score"],
        "cells": cells_payload,
        "ok_count": sum(1 for r in results if r.status == "ok"),
        "fail_count": sum(1 for r in results if r.status != "ok"),
    }
    if plan.configs is not None and plan.step == "all":
        manifest["configs"] = {
            name: plan.configs.resolve(name) for name in plan.variants
        }

    # Stable hash useful for debugging
    manifest["spec_hash"] = hashlib.sha256(
        json.dumps(
            {"step": plan.step, "videos": plan.videos, "variants": plan.variants},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12]

    return manifest


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def dry_run_summary(plan: SweepPlan, runs_base: Path) -> dict[str, Any]:
    """Return the planned cells + cost bracket without executing anything."""
    low_total = 0.0
    high_total = 0.0
    saw_unknown = False
    per_cell: list[dict[str, Any]] = []

    for cell in plan.cells:
        # For full-pipeline, estimate against essay_single since it dominates
        candidate = cell.variant
        if plan.step == "all" and plan.configs is not None:
            candidate = plan.configs.resolve(cell.variant).get(
                "essay_single", llm.MODELS["essay_single"],
            )
        low, high = estimate_cell_cost(cell.video_id, plan.step, candidate, runs_base)
        if low is None or high is None:
            saw_unknown = True
        else:
            low_total += low
            high_total += high
        per_cell.append({
            "video_id": cell.video_id,
            "variant": cell.variant,
            "slug": cell.slug,
            "estimated_low_usd": low,
            "estimated_high_usd": high,
        })

    return {
        "exp_id": plan.exp_id,
        "step": plan.step,
        "cell_count": len(plan.cells),
        "estimated_total_low_usd": None if saw_unknown else round(low_total, 4),
        "estimated_total_high_usd": None if saw_unknown else round(high_total, 4),
        "has_unknown_pricing": saw_unknown,
        "cells": per_cell,
    }
