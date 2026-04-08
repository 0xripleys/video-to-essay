"""Provider-agnostic LLM client for Anthropic and Qwen/vLLM."""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, TypeVar

import anthropic
import openai

ModelClass = Literal["fast", "smart"]

ANTHROPIC_FAST_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_SMART_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_QWEN_MODEL = "qwen3-vl-32b"

_MAX_RETRIES = 5
_VISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "value": {"type": "integer"},
        "description": {"type": "string"},
    },
    "required": ["category", "value", "description"],
}


class LLMResponseParseError(RuntimeError):
    """Raised when a response cannot be parsed into the expected shape."""


@dataclass(frozen=True)
class _Config:
    provider: Literal["anthropic", "qwen"]
    anthropic_fast_model: str
    anthropic_smart_model: str
    qwen_base_url: str | None
    qwen_api_key: str | None
    qwen_model: str
    qwen_max_tokens: int


T = TypeVar("T")


def _normalize_qwen_base_url(raw: str) -> str:
    base = raw.strip().rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _is_anthropic_like_model(model: str | None) -> bool:
    return bool(model and "claude" in model.lower())


@lru_cache(maxsize=1)
def get_config() -> _Config:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider not in {"anthropic", "qwen"}:
        raise RuntimeError(
            "Invalid LLM_PROVIDER. Expected 'anthropic' or 'qwen', "
            f"got: {provider!r}"
        )

    qwen_base_url = os.environ.get("QWEN_BASE_URL")
    qwen_api_key = os.environ.get("QWEN_API_KEY")
    qwen_model = os.environ.get("QWEN_MODEL", DEFAULT_QWEN_MODEL)
    qwen_max_tokens = int(os.environ.get("QWEN_MAX_TOKENS", "4096"))

    if provider == "qwen":
        if not qwen_base_url:
            raise RuntimeError(
                "LLM_PROVIDER=qwen requires QWEN_BASE_URL. "
                "Set it to your Modal endpoint (with or without /v1)."
            )
        if not qwen_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=qwen requires QWEN_API_KEY."
            )
        qwen_base_url = _normalize_qwen_base_url(qwen_base_url)

    return _Config(
        provider=provider,
        anthropic_fast_model=os.environ.get(
            "ANTHROPIC_FAST_MODEL", ANTHROPIC_FAST_MODEL
        ),
        anthropic_smart_model=os.environ.get(
            "ANTHROPIC_SMART_MODEL", ANTHROPIC_SMART_MODEL
        ),
        qwen_base_url=qwen_base_url,
        qwen_api_key=qwen_api_key,
        qwen_model=qwen_model,
        qwen_max_tokens=qwen_max_tokens,
    )


def _effective_max_tokens(cfg: _Config, requested: int) -> int:
    if cfg.provider == "qwen":
        return min(requested, cfg.qwen_max_tokens)
    return requested


def _resolve_model(
    cfg: _Config,
    model_class: ModelClass,
    model: str | None,
) -> str:
    if cfg.provider == "anthropic":
        if model:
            return model
        return (
            cfg.anthropic_fast_model
            if model_class == "fast"
            else cfg.anthropic_smart_model
        )
    if model and not _is_anthropic_like_model(model):
        return model
    return cfg.qwen_model


def _anthropic_client(api_key_override: str | None) -> anthropic.Anthropic:
    if api_key_override:
        return anthropic.Anthropic(api_key=api_key_override)
    return anthropic.Anthropic()


def _qwen_client(cfg: _Config, api_key_override: str | None) -> openai.OpenAI:
    return openai.OpenAI(
        base_url=cfg.qwen_base_url,
        api_key=api_key_override or cfg.qwen_api_key,
    )


def _sleep_backoff(attempt: int) -> None:
    base = min(60.0, 2 ** attempt)
    jitter = random.uniform(0.0, 0.5)
    time.sleep(base + jitter)


def _is_retriable(provider: Literal["anthropic", "qwen"], exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    if provider == "anthropic":
        if isinstance(
            exc,
            (
                anthropic.RateLimitError,
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ),
        ):
            return True
        if isinstance(exc, anthropic.APIStatusError):
            return exc.status_code >= 500
        return False

    if isinstance(
        exc,
        (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ),
    ):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return False


def _call_with_retry(
    provider: Literal["anthropic", "qwen"],
    op_name: str,
    func: Callable[[], T],
) -> T:
    for attempt in range(_MAX_RETRIES):
        try:
            return func()
        except Exception as exc:
            if not _is_retriable(provider, exc) or attempt == _MAX_RETRIES - 1:
                raise
            print(
                f"  {op_name}: transient error, retrying "
                f"({attempt + 1}/{_MAX_RETRIES})..."
            )
            _sleep_backoff(attempt)
    raise RuntimeError("unreachable")


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
    return text


def _parse_json_object(raw: str, *, context: str) -> dict[str, Any]:
    text = _strip_code_fence(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseParseError(
            f"{context}: expected valid JSON object, got: {raw[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise LLMResponseParseError(
            f"{context}: expected JSON object, got {type(parsed).__name__}"
        )
    return parsed


def _anthropic_text(msg: anthropic.types.Message) -> str:
    parts: list[str] = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _openai_messages(
    user: str,
    system: str | None,
    *,
    image: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if image is None:
        messages.append({"role": "user", "content": user})
    else:
        messages.append(
            {
                "role": "user",
                "content": [
                    image,
                    {"type": "text", "text": user},
                ],
            }
        )
    return messages


def text_complete(
    user: str,
    *,
    system: str | None = None,
    max_tokens: int,
    model_class: ModelClass,
    model: str | None = None,
    api_key_override: str | None = None,
) -> str:
    cfg = get_config()
    resolved_model = _resolve_model(cfg, model_class, model)
    max_tokens = _effective_max_tokens(cfg, max_tokens)

    if cfg.provider == "anthropic":
        client = _anthropic_client(api_key_override)
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system

        msg = _call_with_retry(
            cfg.provider, "text_complete", lambda: client.messages.create(**kwargs)
        )
        return _anthropic_text(msg)

    client = _qwen_client(cfg, api_key_override)
    msg = _call_with_retry(
        cfg.provider,
        "text_complete",
        lambda: client.chat.completions.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=_openai_messages(user, system),
        ),
    )
    content = msg.choices[0].message.content
    return content if isinstance(content, str) else ""


def text_stream(
    user: str,
    *,
    system: str | None = None,
    max_tokens: int,
    model_class: ModelClass,
    model: str | None = None,
    api_key_override: str | None = None,
) -> Iterator[str]:
    cfg = get_config()
    resolved_model = _resolve_model(cfg, model_class, model)
    max_tokens = _effective_max_tokens(cfg, max_tokens)

    for attempt in range(_MAX_RETRIES):
        yielded_any = False
        try:
            if cfg.provider == "anthropic":
                client = _anthropic_client(api_key_override)
                kwargs: dict[str, Any] = {
                    "model": resolved_model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": user}],
                }
                if system:
                    kwargs["system"] = system
                with client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        yielded_any = True
                        yield text
                return

            client = _qwen_client(cfg, api_key_override)
            stream = client.chat.completions.create(
                model=resolved_model,
                max_tokens=max_tokens,
                messages=_openai_messages(user, system),
                stream=True,
            )
            for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                delta = choice.delta if choice else None
                text = delta.content if delta else None
                if text:
                    yielded_any = True
                    yield text
            return
        except Exception as exc:
            if yielded_any or not _is_retriable(cfg.provider, exc):
                raise
            if attempt == _MAX_RETRIES - 1:
                raise
            print(
                f"  text_stream: transient error, retrying "
                f"({attempt + 1}/{_MAX_RETRIES})..."
            )
            _sleep_backoff(attempt)


def text_complete_with_tool(
    user: str,
    *,
    system: str | None = None,
    max_tokens: int,
    model_class: ModelClass,
    tool_name: str,
    tool_description: str,
    tool_schema: dict[str, Any],
    model: str | None = None,
    api_key_override: str | None = None,
) -> dict[str, Any]:
    cfg = get_config()
    resolved_model = _resolve_model(cfg, model_class, model)
    max_tokens = _effective_max_tokens(cfg, max_tokens)

    if cfg.provider == "anthropic":
        client = _anthropic_client(api_key_override)
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": tool_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system:
            kwargs["system"] = system

        msg = _call_with_retry(
            cfg.provider,
            "text_complete_with_tool",
            lambda: client.messages.create(**kwargs),
        )
        for block in msg.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            block_input = getattr(block, "input", None)
            if isinstance(block_input, dict):
                return block_input
        raise LLMResponseParseError(
            "text_complete_with_tool: Anthropic response missing tool payload"
        )

    client = _qwen_client(cfg, api_key_override)
    msg = _call_with_retry(
        cfg.provider,
        "text_complete_with_tool",
        lambda: client.chat.completions.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=_openai_messages(user, system),
            extra_body={"guided_json": tool_schema},
        ),
    )
    content = msg.choices[0].message.content
    if not isinstance(content, str):
        raise LLMResponseParseError(
            "text_complete_with_tool: Qwen response content was not text"
        )
    return _parse_json_object(content, context="text_complete_with_tool")


def vision_classify(
    user: str,
    *,
    image_b64: str,
    image_media_type: str = "image/jpeg",
    max_tokens: int,
    model_class: ModelClass,
    model: str | None = None,
    api_key_override: str | None = None,
) -> dict[str, Any]:
    cfg = get_config()
    resolved_model = _resolve_model(cfg, model_class, model)
    max_tokens = _effective_max_tokens(cfg, max_tokens)

    if cfg.provider == "anthropic":
        client = _anthropic_client(api_key_override)
        msg = _call_with_retry(
            cfg.provider,
            "vision_classify",
            lambda: client.messages.create(
                model=resolved_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": image_media_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": user},
                        ],
                    }
                ],
            ),
        )
        return _parse_json_object(_anthropic_text(msg), context="vision_classify")

    client = _qwen_client(cfg, api_key_override)
    msg = _call_with_retry(
        cfg.provider,
        "vision_classify",
        lambda: client.chat.completions.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=_openai_messages(
                user,
                None,
                image={
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{image_b64}"
                    },
                },
            ),
            extra_body={"guided_json": _VISION_SCHEMA},
        ),
    )
    content = msg.choices[0].message.content
    if not isinstance(content, str):
        raise LLMResponseParseError(
            "vision_classify: Qwen response content was not text"
        )
    return _parse_json_object(content, context="vision_classify")
