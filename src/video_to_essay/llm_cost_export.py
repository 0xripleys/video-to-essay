"""Export persisted LLM call costs from S3 run artifacts."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import litellm


CSV_FIELDS = [
    "s3_key",
    "video_id",
    "step",
    "call_file",
    "task",
    "model",
    "response_model",
    "request_id",
    "timestamp_ms",
    "timestamp_iso_utc",
    "wall_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "input_text_tokens",
    "output_text_tokens",
    "reasoning_tokens",
    "image_tokens",
    "max_tokens",
    "cost_usd_recorded",
    "cost_usd_estimated",
    "cost_usd",
    "cost_source",
    "object_size",
    "last_modified",
    "parse_error",
]


def is_llm_call_key(key: str) -> bool:
    """Return True for run artifact keys shaped like llm call JSON files."""
    parts = key.split("/")
    return (
        len(parts) >= 5
        and parts[0] == "runs"
        and "llm_calls" in parts
        and key.endswith(".json")
    )


def parse_key(key: str) -> dict[str, str]:
    """Extract run identity from an S3 key."""
    parts = key.split("/")
    if len(parts) < 5 or parts[0] != "runs":
        return {"video_id": "", "step": "", "call_file": parts[-1] if parts else ""}

    try:
        calls_idx = parts.index("llm_calls")
    except ValueError:
        calls_idx = -1

    return {
        "video_id": parts[1],
        "step": "/".join(parts[2:calls_idx]) if calls_idx > 2 else parts[2],
        "call_file": parts[-1],
    }


def timestamp_iso(timestamp_ms: Any) -> str:
    """Convert millisecond epoch timestamps to ISO-8601 UTC strings."""
    if timestamp_ms in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(float(timestamp_ms) / 1000, UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _usage(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response")
    if not isinstance(response, dict):
        return {}
    usage = response.get("usage")
    return usage if isinstance(usage, dict) else {}


def _details(usage: dict[str, Any], key: str) -> dict[str, Any]:
    details = usage.get(key)
    return details if isinstance(details, dict) else {}


def estimate_cost_usd(payload: dict[str, Any]) -> float | None:
    """Estimate call cost from token counts using LiteLLM's pricing map."""
    usage = _usage(payload)
    prompt_details = _details(usage, "prompt_tokens_details")

    model = payload.get("model")
    input_tokens = _as_int(payload.get("input_tokens")) or _as_int(
        usage.get("prompt_tokens")
    )
    output_tokens = _as_int(payload.get("output_tokens")) or _as_int(
        usage.get("completion_tokens")
    )
    cache_creation = _as_int(usage.get("cache_creation_input_tokens"))
    if cache_creation is None:
        cache_creation = _as_int(prompt_details.get("cache_creation_tokens"))
    cache_read = _as_int(usage.get("cache_read_input_tokens"))
    if cache_read is None:
        cache_read = _as_int(prompt_details.get("cached_tokens"))

    if not model or (input_tokens is None and output_tokens is None):
        return None

    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=str(model),
            prompt_tokens=input_tokens or 0,
            completion_tokens=output_tokens or 0,
            cache_creation_input_tokens=cache_creation or 0,
            cache_read_input_tokens=cache_read or 0,
        )
    except Exception:
        return None

    if prompt_cost is None or completion_cost is None:
        return None
    return float(prompt_cost) + float(completion_cost)


def row_from_payload(
    key: str,
    payload: dict[str, Any],
    *,
    object_size: int | None = None,
    last_modified: str | None = None,
) -> dict[str, str]:
    """Build one CSV row from a persisted LLM call payload."""
    key_parts = parse_key(key)
    usage = _usage(payload)
    prompt_details = _details(usage, "prompt_tokens_details")
    completion_details = _details(usage, "completion_tokens_details")

    input_tokens = _as_int(payload.get("input_tokens")) or _as_int(
        usage.get("prompt_tokens")
    )
    output_tokens = _as_int(payload.get("output_tokens")) or _as_int(
        usage.get("completion_tokens")
    )
    total_tokens = _as_int(usage.get("total_tokens"))
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    cache_creation = _as_int(usage.get("cache_creation_input_tokens"))
    if cache_creation is None:
        cache_creation = _as_int(prompt_details.get("cache_creation_tokens"))
    cache_read = _as_int(usage.get("cache_read_input_tokens"))
    if cache_read is None:
        cache_read = _as_int(prompt_details.get("cached_tokens"))

    recorded_cost = _as_float(payload.get("cost_usd"))
    estimated_cost = estimate_cost_usd(payload)
    final_cost = recorded_cost if recorded_cost is not None else estimated_cost
    if recorded_cost is not None:
        cost_source = "recorded"
    elif estimated_cost is not None:
        cost_source = "estimated"
    else:
        cost_source = "unknown"

    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    kwargs = payload.get("kwargs") if isinstance(payload.get("kwargs"), dict) else {}
    timestamp_ms = payload.get("timestamp_ms")

    row: dict[str, Any] = {
        **key_parts,
        "s3_key": key,
        "task": payload.get("task"),
        "model": payload.get("model"),
        "response_model": response.get("model") if isinstance(response, dict) else "",
        "request_id": payload.get("request_id"),
        "timestamp_ms": timestamp_ms,
        "timestamp_iso_utc": timestamp_iso(timestamp_ms),
        "wall_ms": payload.get("wall_ms"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "input_text_tokens": prompt_details.get("text_tokens"),
        "output_text_tokens": completion_details.get("text_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "image_tokens": prompt_details.get("image_tokens"),
        "max_tokens": kwargs.get("max_tokens") if isinstance(kwargs, dict) else "",
        "cost_usd_recorded": _money(recorded_cost),
        "cost_usd_estimated": _money(estimated_cost),
        "cost_usd": _money(final_cost),
        "cost_source": cost_source,
        "object_size": object_size,
        "last_modified": last_modified or "",
        "parse_error": "",
    }
    return {field: "" if row.get(field) is None else str(row.get(field)) for field in CSV_FIELDS}


def error_row(
    key: str,
    error: str,
    *,
    object_size: int | None = None,
    last_modified: str | None = None,
) -> dict[str, str]:
    """Build a CSV row for an unreadable or invalid JSON object."""
    row = {
        **parse_key(key),
        "s3_key": key,
        "object_size": object_size,
        "last_modified": last_modified or "",
        "parse_error": error,
        "cost_source": "unknown",
    }
    return {field: "" if row.get(field) is None else str(row.get(field, "")) for field in CSV_FIELDS}


def iter_llm_call_objects(client: Any, bucket: str, prefix: str = "runs/") -> Iterator[dict[str, Any]]:
    """Yield S3 object metadata for persisted LLM call JSON files."""
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if is_llm_call_key(key):
                yield obj


def export_rows_to_csv(rows: Iterable[dict[str, str]], output_path: str) -> int:
    """Write rows to CSV and return the number of rows written."""
    count = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def rows_from_s3(client: Any, bucket: str, prefix: str = "runs/") -> Iterator[dict[str, str]]:
    """Download and parse all persisted LLM call objects under an S3 prefix."""
    for obj in iter_llm_call_objects(client, bucket, prefix):
        key = obj["Key"]
        last_modified = obj.get("LastModified")
        last_modified_str = last_modified.isoformat() if last_modified else ""
        size = obj.get("Size")
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            raw = response["Body"].read()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                yield error_row(
                    key,
                    "JSON root is not an object",
                    object_size=size,
                    last_modified=last_modified_str,
                )
                continue
        except Exception as e:
            yield error_row(
                key,
                f"{type(e).__name__}: {e}",
                object_size=size,
                last_modified=last_modified_str,
            )
            continue

        yield row_from_payload(
            key,
            payload,
            object_size=size,
            last_modified=last_modified_str,
        )
