"""Single entry point for all LLM calls in the pipeline.

Models are selected per-task. Defaults live in MODELS below. Pass `model=`
explicitly to override (used by the --model CLI flag for experimentation).

Calls inside `with llm.run_context(step_dir):` are persisted as JSON to
`<step_dir>/llm_calls/<task>_<ms>.json` for debugging and replay. Outside
a run_context, persistence is a no-op (e.g., during tests).
"""

import contextvars
import hashlib
import json
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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

_step_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "step_dir", default=None
)


@contextmanager
def run_context(step_dir: Path) -> Generator[None, None, None]:
    """Persist LLM calls inside this block to `<step_dir>/llm_calls/`."""
    token = _step_dir.set(Path(step_dir))
    try:
        yield
    finally:
        _step_dir.reset(token)


def complete(
    task: str,
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """Non-streaming LLM call. Returns the full litellm ModelResponse."""
    resolved = model or MODELS[task]
    response = litellm.completion(model=resolved, messages=messages, **kwargs)
    _persist(task, resolved, messages, kwargs, response)
    return response


def stream(
    task: str,
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    **kwargs: Any,
) -> Generator[str, None, None]:
    """Streaming LLM call. Yields delta strings.

    Used for long-running essay/place_images requests to avoid the
    non-streaming long-request timeout. Persists the assembled response
    after the stream drains.
    """
    resolved = model or MODELS[task]
    response = litellm.completion(
        model=resolved, messages=messages, stream=True, **kwargs
    )
    chunks: list[Any] = []
    for chunk in response:
        chunks.append(chunk)
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
    assembled = litellm.stream_chunk_builder(chunks, messages=messages)
    if assembled is not None:
        _persist(task, resolved, messages, kwargs, assembled)


def _persist(
    task: str,
    resolved_model: str,
    messages: list[dict[str, Any]],
    kwargs: dict[str, Any],
    response: ModelResponse,
) -> None:
    step_dir = _step_dir.get()
    if step_dir is None:
        return

    calls_dir = step_dir / "llm_calls"
    calls_dir.mkdir(parents=True, exist_ok=True)

    timestamp_ms = int(time.time() * 1000)
    path = calls_dir / f"{task}_{timestamp_ms}.json"

    usage = getattr(response, "usage", None)
    payload = {
        "task": task,
        "model": resolved_model,
        "timestamp_ms": timestamp_ms,
        "request_id": _extract_request_id(response),
        "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "output_tokens": (
            getattr(usage, "completion_tokens", None) if usage else None
        ),
        "messages": _strip_image_bytes(messages),
        "kwargs": _serialize_kwargs(kwargs),
        "response": response.model_dump() if hasattr(response, "model_dump") else None,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))


def _extract_request_id(response: ModelResponse) -> str | None:
    """Pull the provider's request ID from response headers if present.

    LiteLLM nests provider headers in `_hidden_params['additional_headers']`
    with an `llm_provider-` prefix. Anthropic uses `request-id`; OpenAI uses
    `x-request-id`.
    """
    hidden = getattr(response, "_hidden_params", None) or {}
    headers = hidden.get("additional_headers") or {}
    return (
        headers.get("llm_provider-request-id")
        or headers.get("llm_provider-x-request-id")
        or headers.get("request-id")
        or headers.get("x-request-id")
    )


def _strip_image_bytes(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace base64 image data URLs with size+hash references.

    Leaves https:// URLs alone. Avoids storing tens of MB of redundant
    image bytes in persisted call logs (frames are already on S3).
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_content = [_strip_image_block(block) for block in content]
            out.append({**msg, "content": new_content})
        else:
            out.append(msg)
    return out


def _strip_image_block(block: Any) -> Any:
    if not isinstance(block, dict):
        return block
    if block.get("type") != "image_url":
        return block
    url_obj = block.get("image_url") or {}
    url = url_obj.get("url", "")
    if not url.startswith("data:"):
        return block

    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        return block

    raw = b64.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    size_kb = len(raw) * 3 // 4 // 1024  # rough decoded size
    placeholder = f"<base64 image, sha256:{digest}, ~{size_kb}kb>"
    return {
        **block,
        "image_url": {**url_obj, "url": placeholder, "_stripped_header": header},
    }


def _serialize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Make kwargs JSON-serializable (strip unhashable / non-serializable values)."""
    out: dict[str, Any] = {}
    for k, v in kwargs.items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            out[k] = repr(v)
    return out
