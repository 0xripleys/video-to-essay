"""Tests for exporting persisted LLM call costs."""

from unittest.mock import patch

from video_to_essay import llm_cost_export


def test_is_llm_call_key_matches_run_call_json() -> None:
    assert llm_cost_export.is_llm_call_key(
        "runs/video123/03_essay/llm_calls/essay_multi_123.json"
    )
    assert not llm_cost_export.is_llm_call_key("runs/video123/03_essay/essay.md")
    assert not llm_cost_export.is_llm_call_key(
        "experiments/exp/video123/essay/variant/llm_calls/essay_multi_123.json"
    )


def test_parse_key_extracts_video_step_and_file() -> None:
    assert llm_cost_export.parse_key(
        "runs/video123/03_essay/llm_calls/essay_multi_123.json"
    ) == {
        "video_id": "video123",
        "step": "03_essay",
        "call_file": "essay_multi_123.json",
    }


def test_row_from_payload_uses_recorded_cost_when_present() -> None:
    payload = {
        "task": "essay_multi",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "timestamp_ms": 1777499666875,
        "request_id": "req_123",
        "input_tokens": 3258,
        "output_tokens": 2213,
        "wall_ms": 1200,
        "cost_usd": 0.012345,
        "kwargs": {"max_tokens": 64000},
        "response": {
            "model": "claude-sonnet-4-5-20250929",
            "usage": {
                "prompt_tokens": 3258,
                "completion_tokens": 2213,
                "total_tokens": 5471,
                "prompt_tokens_details": {
                    "cached_tokens": 100,
                    "text_tokens": 3158,
                    "image_tokens": 0,
                    "cache_creation_tokens": 25,
                },
                "completion_tokens_details": {
                    "text_tokens": 2213,
                    "reasoning_tokens": 0,
                },
            },
        },
    }

    with patch.object(llm_cost_export, "estimate_cost_usd", return_value=0.011):
        row = llm_cost_export.row_from_payload(
            "runs/video123/03_essay/llm_calls/essay_multi_123.json",
            payload,
            object_size=500,
            last_modified="2026-05-08T00:00:00+00:00",
        )

    assert row["video_id"] == "video123"
    assert row["step"] == "03_essay"
    assert row["task"] == "essay_multi"
    assert row["request_id"] == "req_123"
    assert row["input_tokens"] == "3258"
    assert row["output_tokens"] == "2213"
    assert row["total_tokens"] == "5471"
    assert row["cache_creation_input_tokens"] == "25"
    assert row["cache_read_input_tokens"] == "100"
    assert row["max_tokens"] == "64000"
    assert row["cost_usd_recorded"] == "0.012345"
    assert row["cost_usd_estimated"] == "0.011"
    assert row["cost_usd"] == "0.012345"
    assert row["cost_source"] == "recorded"
    assert row["object_size"] == "500"


def test_row_from_payload_uses_estimated_cost_when_recorded_missing() -> None:
    payload = {
        "task": "sponsor_filter",
        "model": "anthropic/claude-haiku-4-5-20251001",
        "input_tokens": 1000,
        "output_tokens": 50,
        "response": {"usage": {"total_tokens": 1050}},
    }

    with patch.object(llm_cost_export, "estimate_cost_usd", return_value=0.00042):
        row = llm_cost_export.row_from_payload(
            "runs/video123/02_filter_sponsors/llm_calls/sponsor_filter_123.json",
            payload,
        )

    assert row["cost_usd_recorded"] == ""
    assert row["cost_usd_estimated"] == "0.00042"
    assert row["cost_usd"] == "0.00042"
    assert row["cost_source"] == "estimated"


def test_error_row_preserves_key_context() -> None:
    row = llm_cost_export.error_row(
        "runs/video123/03_essay/llm_calls/bad.json",
        "JSONDecodeError: invalid",
    )

    assert row["video_id"] == "video123"
    assert row["step"] == "03_essay"
    assert row["call_file"] == "bad.json"
    assert row["parse_error"] == "JSONDecodeError: invalid"
    assert row["cost_source"] == "unknown"
