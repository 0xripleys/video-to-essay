"""Tests for the LLM wrapper module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_to_essay import llm


def test_strip_image_bytes_replaces_data_url() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQAAAA"},
                },
            ],
        }
    ]
    out = llm._strip_image_bytes(messages)
    url = out[0]["content"][1]["image_url"]["url"]
    assert url.startswith("<base64 image, sha256:")
    assert "kb>" in url
    assert "9j/4AAQ" not in url


def test_strip_image_bytes_preserves_https_url() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://s3.example.com/frame_0042.jpg"},
                },
            ],
        }
    ]
    out = llm._strip_image_bytes(messages)
    assert out[0]["content"][0]["image_url"]["url"] == (
        "https://s3.example.com/frame_0042.jpg"
    )


def test_strip_image_bytes_handles_text_only_messages() -> None:
    messages = [{"role": "user", "content": "hello"}]
    out = llm._strip_image_bytes(messages)
    assert out == messages


def test_strip_image_bytes_does_not_mutate_input() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,abc"},
                },
            ],
        }
    ]
    original = json.dumps(messages)
    llm._strip_image_bytes(messages)
    assert json.dumps(messages) == original


def _make_mock_response() -> MagicMock:
    response = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.model_dump.return_value = {"id": "msg_123", "choices": []}
    response._hidden_params = {
        "additional_headers": {"llm_provider-request-id": "req_abc123"},
    }
    return response


def test_persist_writes_json_when_context_set(tmp_path: Path) -> None:
    response = _make_mock_response()
    with llm.run_context(tmp_path):
        llm._persist(
            task="summarize",
            resolved_model="anthropic/claude-haiku",
            messages=[{"role": "user", "content": "hi"}],
            kwargs={"max_tokens": 100},
            response=response,
        )

    files = list((tmp_path / "llm_calls").glob("summarize_*.json"))
    assert len(files) == 1

    payload = json.loads(files[0].read_text())
    assert payload["task"] == "summarize"
    assert payload["model"] == "anthropic/claude-haiku"
    assert payload["request_id"] == "req_abc123"
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 50
    assert payload["kwargs"] == {"max_tokens": 100}


def test_persist_noop_when_context_unset(tmp_path: Path) -> None:
    response = _make_mock_response()
    llm._persist(
        task="summarize",
        resolved_model="anthropic/claude-haiku",
        messages=[],
        kwargs={},
        response=response,
    )
    assert not (tmp_path / "llm_calls").exists()


def test_run_context_resets_after_exit(tmp_path: Path) -> None:
    assert llm._step_dir.get() is None
    with llm.run_context(tmp_path):
        assert llm._step_dir.get() == tmp_path
    assert llm._step_dir.get() is None


def test_complete_resolves_model_from_models_dict() -> None:
    with patch.object(llm.litellm, "completion") as mock_completion:
        mock_completion.return_value = _make_mock_response()
        llm.complete(task="summarize", messages=[{"role": "user", "content": "hi"}])

    assert mock_completion.call_args.kwargs["model"] == llm.MODELS["summarize"]


def test_complete_uses_explicit_override() -> None:
    with patch.object(llm.litellm, "completion") as mock_completion:
        mock_completion.return_value = _make_mock_response()
        llm.complete(
            task="summarize",
            messages=[{"role": "user", "content": "hi"}],
            model="openai/gpt-5",
        )

    assert mock_completion.call_args.kwargs["model"] == "openai/gpt-5"


def test_complete_unknown_task_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        llm.complete(task="not_a_real_task", messages=[])


def test_serialize_kwargs_handles_non_serializable() -> None:
    class NotSerializable:
        def __repr__(self) -> str:
            return "<NotSerializable>"

    out = llm._serialize_kwargs({"good": 1, "bad": NotSerializable()})
    assert out["good"] == 1
    assert out["bad"] == "<NotSerializable>"
