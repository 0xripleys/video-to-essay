"""Unit tests for the experiment harness orchestrator."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from video_to_essay import experiment
from video_to_essay.experiment import (
    CellPlan,
    ExperimentConfigs,
    build_sweep,
    dry_run_summary,
    load_configs,
    make_exp_id,
    run_cell,
    run_sweep,
    slug_for_model,
    sum_costs_from_llm_calls,
)


# ---------------------------------------------------------------------------
# IDs and slugs
# ---------------------------------------------------------------------------

def test_make_exp_id_format() -> None:
    eid = make_exp_id("essay")
    parts = eid.split("-")
    assert len(parts) == 4
    assert parts[2] == "essay"
    assert len(parts[3]) == 4  # short hash


def test_make_exp_id_with_label() -> None:
    eid = make_exp_id("essay", "my-test")
    assert eid.endswith("-my-test")


def test_make_exp_id_sanitizes_label() -> None:
    eid = make_exp_id("essay", "weird/path:label")
    assert "/" not in eid and ":" not in eid


def test_slug_for_model_replaces_slash() -> None:
    assert slug_for_model("anthropic/claude-sonnet-4-5") == "anthropic--claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_load_configs_basic(tmp_path: Path) -> None:
    yml = tmp_path / "experiments.yaml"
    yml.write_text(
        "configs:\n"
        "  baseline: {}\n"
        "  cheap-mix:\n"
        "    essay_single: openai/gpt-5-mini\n"
    )
    cfgs = load_configs(yml)
    assert cfgs.configs["baseline"] == {}
    assert cfgs.configs["cheap-mix"]["essay_single"] == "openai/gpt-5-mini"


def test_load_configs_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_configs(tmp_path / "nope.yaml")


def test_load_configs_rejects_non_mapping(tmp_path: Path) -> None:
    yml = tmp_path / "bad.yaml"
    yml.write_text("configs: [1, 2, 3]\n")
    with pytest.raises(ValueError):
        load_configs(yml)


def test_resolve_merges_with_models(tmp_path: Path) -> None:
    cfgs = ExperimentConfigs(configs={"swap": {"essay_single": "openai/gpt-5"}})
    merged = cfgs.resolve("swap")
    assert merged["essay_single"] == "openai/gpt-5"
    # Other keys preserved from MODELS
    from video_to_essay import llm
    assert merged["score"] == llm.MODELS["score"]


def test_resolve_unknown_config_raises() -> None:
    cfgs = ExperimentConfigs(configs={})
    with pytest.raises(KeyError):
        cfgs.resolve("nope")


# ---------------------------------------------------------------------------
# Sweep building / validation
# ---------------------------------------------------------------------------

def test_build_sweep_single_step_requires_models() -> None:
    with pytest.raises(ValueError, match="requires --models"):
        build_sweep("essay", ["v1"], models=None, config_names=None)


def test_build_sweep_single_step_rejects_configs() -> None:
    with pytest.raises(ValueError, match="rejects --configs"):
        build_sweep("essay", ["v1"], models=["m"], config_names=["c"])


def test_build_sweep_all_requires_configs() -> None:
    with pytest.raises(ValueError, match="requires --configs"):
        build_sweep("all", ["v1"], models=None, config_names=None)


def test_build_sweep_all_rejects_models() -> None:
    cfgs = ExperimentConfigs(configs={"baseline": {}})
    with pytest.raises(ValueError, match="rejects --models"):
        build_sweep("all", ["v1"], models=["m"], config_names=["baseline"], configs=cfgs)


def test_build_sweep_unknown_config_raises() -> None:
    cfgs = ExperimentConfigs(configs={"baseline": {}})
    with pytest.raises(ValueError, match="unknown config"):
        build_sweep("all", ["v1"], config_names=["nope"], configs=cfgs)


def test_build_sweep_unknown_step_raises() -> None:
    with pytest.raises(ValueError, match="unknown step"):
        build_sweep("not_a_step", ["v1"], models=["m"])


def test_build_sweep_cartesian_product() -> None:
    with patch("litellm.utils.get_llm_provider", return_value=("anthropic", "anthropic", None, None)):
        plan = build_sweep(
            "essay",
            ["v1", "v2", "v3"],
            models=["anthropic/claude-sonnet-4-5", "openai/gpt-5"],
        )
    assert len(plan.cells) == 6
    # All combinations present
    keys = {(c.video_id, c.variant) for c in plan.cells}
    assert keys == {
        ("v1", "anthropic/claude-sonnet-4-5"), ("v1", "openai/gpt-5"),
        ("v2", "anthropic/claude-sonnet-4-5"), ("v2", "openai/gpt-5"),
        ("v3", "anthropic/claude-sonnet-4-5"), ("v3", "openai/gpt-5"),
    }


# ---------------------------------------------------------------------------
# Input fetching
# ---------------------------------------------------------------------------

def test_fetch_step_inputs_uses_local(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _seed_canonical_inputs(runs, "vid1")
    (runs / "vid1" / "01_transcript" / "transcript.txt").write_text("hello")
    (runs / "vid1" / "02_filter_sponsors" / "transcript_clean.txt").write_text("hello")

    work = tmp_path / "work"
    paths = experiment.fetch_step_inputs("vid1", "essay", work, runs_base=runs)
    assert "01_transcript/transcript.txt" in paths
    assert "02_filter_sponsors/transcript_clean.txt" in paths
    assert paths["02_filter_sponsors/transcript_clean.txt"].read_text() == "hello"


def test_fetch_step_inputs_falls_back_to_s3(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    work = tmp_path / "work"

    with patch.object(experiment.s3, "download_file", return_value=b"s3-bytes") as mock_dl:
        paths = experiment.fetch_step_inputs("vid1", "summarize", work, runs_base=runs)

    assert mock_dl.called
    assert paths["03_essay/essay.md"].read_bytes() == b"s3-bytes"


def test_fetch_step_inputs_missing_raises(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    work = tmp_path / "work"
    with patch.object(experiment.s3, "download_file", side_effect=Exception("404")):
        with pytest.raises(FileNotFoundError, match="missing input"):
            experiment.fetch_step_inputs("vid1", "summarize", work, runs_base=runs)


# ---------------------------------------------------------------------------
# Cost summing
# ---------------------------------------------------------------------------

def test_sum_costs_from_llm_calls(tmp_path: Path) -> None:
    calls = tmp_path / "llm_calls"
    calls.mkdir()
    (calls / "essay_001.json").write_text(json.dumps({
        "task": "essay_single", "cost_usd": 0.10,
    }))
    (calls / "score_002.json").write_text(json.dumps({
        "task": "score", "cost_usd": 0.05,
    }))
    total, per = sum_costs_from_llm_calls(tmp_path)
    assert total == 0.15
    assert per == {"essay_single": 0.10, "score": 0.05}


def test_sum_costs_returns_none_when_unknown(tmp_path: Path) -> None:
    calls = tmp_path / "llm_calls"
    calls.mkdir()
    (calls / "a.json").write_text(json.dumps({"task": "x", "cost_usd": 0.10}))
    (calls / "b.json").write_text(json.dumps({"task": "y", "cost_usd": None}))
    total, _ = sum_costs_from_llm_calls(tmp_path)
    assert total is None


# ---------------------------------------------------------------------------
# Cell execution
# ---------------------------------------------------------------------------

def _seed_canonical_inputs(runs: Path, video_id: str) -> None:
    """Create a minimal runs/<video_id>/ tree."""
    (runs / video_id / "01_transcript").mkdir(parents=True)
    (runs / video_id / "01_transcript" / "transcript.txt").write_text(
        "[00:00] hello world"
    )
    (runs / video_id / "02_filter_sponsors").mkdir(parents=True)
    (runs / video_id / "02_filter_sponsors" / "sponsor_segments.json").write_text("[]")
    (runs / video_id / "02_filter_sponsors" / "transcript_clean.txt").write_text(
        "[00:00] hello world"
    )


def test_run_cell_essay_success(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    _seed_canonical_inputs(runs, "v1")

    plan = CellPlan(video_id="v1", step="essay", variant="m/x", slug="m--x")

    fake_essay = "# Essay\n\nThis is a test essay."
    fake_score = {"overall_score": 8.4, "dimensions": {}, "summary": "great", "model": "judge"}

    with patch.object(experiment, "transcript_to_essay", return_value=fake_essay), \
         patch.object(experiment, "score_essay", return_value=fake_score):
        result = run_cell(plan, "exp1", work, runs, configs=None, upload=False)

    assert result.status == "ok"
    assert result.score_overall == 8.4
    variant_dir = work / "v1" / "essay" / "m--x"
    assert (variant_dir / "output" / "essay.md").read_text() == fake_essay
    assert (variant_dir / "score.json").exists()
    meta = json.loads((variant_dir / "meta.json").read_text())
    assert meta["status"] == "ok"
    assert meta["score_overall"] == 8.4


def test_run_cell_captures_failure(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    _seed_canonical_inputs(runs, "v1")
    plan = CellPlan(video_id="v1", step="essay", variant="m/x", slug="m--x")

    with patch.object(experiment, "transcript_to_essay", side_effect=RuntimeError("boom")):
        result = run_cell(plan, "exp1", work, runs, configs=None, upload=False)

    assert result.status.startswith("failed:")
    meta = json.loads((work / "v1" / "essay" / "m--x" / "meta.json").read_text())
    assert meta["status"].startswith("failed:")


def test_run_cell_essay_score_failure_does_not_fail_cell(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    work = tmp_path / "work"
    work.mkdir()
    _seed_canonical_inputs(runs, "v1")
    plan = CellPlan(video_id="v1", step="essay", variant="m/x", slug="m--x")

    with patch.object(experiment, "transcript_to_essay", return_value="# E"), \
         patch.object(experiment, "score_essay", side_effect=RuntimeError("rate limit")):
        result = run_cell(plan, "exp1", work, runs, configs=None, upload=False)

    assert result.status == "ok"
    assert result.score_overall is None
    meta = json.loads((work / "v1" / "essay" / "m--x" / "meta.json").read_text())
    assert meta["score_status"].startswith("failed:")


# ---------------------------------------------------------------------------
# Sweep run + manifest
# ---------------------------------------------------------------------------

def test_run_sweep_writes_manifest(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "experiments"
    _seed_canonical_inputs(runs, "v1")
    _seed_canonical_inputs(runs, "v2")

    with patch("litellm.utils.get_llm_provider", return_value=("anthropic", "x", None, None)):
        plan = build_sweep("essay", ["v1", "v2"], models=["m1", "m2"])

    with patch.object(experiment, "transcript_to_essay", return_value="# E"), \
         patch.object(experiment, "score_essay", return_value={
             "overall_score": 7.5, "dimensions": {}, "summary": "", "model": "j",
         }):
        manifest = run_sweep(
            plan, concurrency=2, runs_base=runs, output_base=out, upload=False,
        )

    assert manifest["ok_count"] == 4
    assert manifest["fail_count"] == 0
    assert len(manifest["cells"]) == 4
    saved = json.loads((out / plan.exp_id / "manifest.json").read_text())
    assert saved["exp_id"] == plan.exp_id


def test_run_sweep_one_cell_failure_does_not_kill_others(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "experiments"
    _seed_canonical_inputs(runs, "v1")
    _seed_canonical_inputs(runs, "v2")
    with patch("litellm.utils.get_llm_provider", return_value=("anthropic", "x", None, None)):
        plan = build_sweep("essay", ["v1", "v2"], models=["m1"])

    call_count = {"n": 0}
    def _maybe_fail(*_args: object, **_kw: object) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first call boom")
        return "# essay"

    with patch.object(experiment, "transcript_to_essay", side_effect=_maybe_fail), \
         patch.object(experiment, "score_essay", return_value={
             "overall_score": 7.0, "dimensions": {}, "summary": "", "model": "j",
         }):
        manifest = run_sweep(
            plan, concurrency=1, runs_base=runs, output_base=out, upload=False,
        )

    assert manifest["fail_count"] == 1
    assert manifest["ok_count"] == 1


# ---------------------------------------------------------------------------
# Dry-run cost estimation
# ---------------------------------------------------------------------------

def test_dry_run_summary_unknown_when_no_canonical_data(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _seed_canonical_inputs(runs, "v1")
    with patch("litellm.utils.get_llm_provider", return_value=("anthropic", "x", None, None)):
        plan = build_sweep("essay", ["v1"], models=["anthropic/claude-haiku-4-5-20251001"])
    summary = dry_run_summary(plan, runs_base=runs)
    assert summary["cell_count"] == 1
    assert summary["has_unknown_pricing"] is True


def test_dry_run_summary_with_canonical_tokens(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _seed_canonical_inputs(runs, "v1")
    # Plant a canonical llm_calls entry the estimator will read
    calls = runs / "v1" / "03_essay" / "llm_calls"
    calls.mkdir(parents=True)
    (calls / "essay_001.json").write_text(json.dumps({
        "task": "essay_single",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.01,
    }))

    with patch("litellm.utils.get_llm_provider", return_value=("anthropic", "x", None, None)), \
         patch("litellm.cost_per_token", return_value=(0.003, 0.015)):
        plan = build_sweep("essay", ["v1"], models=["anthropic/claude-haiku"])
        summary = dry_run_summary(plan, runs_base=runs)

    assert summary["has_unknown_pricing"] is False
    assert summary["estimated_total_low_usd"] is not None
    assert summary["estimated_total_low_usd"] < summary["estimated_total_high_usd"]
