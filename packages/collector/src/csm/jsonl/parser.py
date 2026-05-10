"""Parse one Claude Code JSONL line into ``transcript_messages`` shape.

Format observed in Claude Code transcripts:

- Top-level ``type``: ``user`` | ``assistant`` | ``system`` | ``summary`` | ``tool_use`` | ``tool_result``
- For ``assistant``: ``message.model``, ``message.usage.{input_tokens,
  output_tokens, cache_creation_input_tokens, cache_read_input_tokens}``,
  ``message.content`` (list of text/tool_use blocks)
- ``timestamp``: ISO 8601, sometimes missing — fall back to ingest time

Borrowed parser shape from ``ryoppippi/ccusage`` (TypeScript) — re-implemented,
not vendored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ParsedMessage:
    role: str
    timestamp: str
    content_json: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class ParseError(ValueError):
    """Raised when a line is not a valid JSONL message."""


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_role(raw: dict[str, object]) -> str:
    """Pick the best role label.

    Claude Code uses both ``type`` (outer) and ``message.role`` (inner).
    We prefer the outer ``type`` because it disambiguates ``tool_result``
    and ``summary`` entries.
    """
    t = raw.get("type")
    if isinstance(t, str) and t:
        return t
    msg = raw.get("message")
    if isinstance(msg, dict):
        role = msg.get("role")
        if isinstance(role, str) and role:
            return role
    return "unknown"


def _extract_timestamp(raw: dict[str, object]) -> str:
    ts = raw.get("timestamp")
    if isinstance(ts, str) and ts:
        return ts
    return _now_iso()


def _extract_assistant_metadata(raw: dict[str, object]) -> dict[str, object]:
    """Pull model + usage off an assistant message. Empty dict otherwise."""
    msg = raw.get("message")
    if not isinstance(msg, dict):
        return {}
    model = msg.get("model")
    usage = msg.get("usage")
    out: dict[str, object] = {}
    if isinstance(model, str):
        out["model"] = model
    if isinstance(usage, dict):
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            v = usage.get(k)
            if isinstance(v, int):
                out[k] = v
    return out


def parse_line(raw: str) -> ParsedMessage:
    """Parse one JSONL line into a :class:`ParsedMessage`.

    Raises :class:`ParseError` for malformed JSON or missing essentials.
    """
    raw = raw.strip()
    if not raw:
        raise ParseError("empty line")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ParseError(f"expected object, got {type(obj).__name__}")

    role = _extract_role(obj)
    timestamp = _extract_timestamp(obj)
    extras = _extract_assistant_metadata(obj) if role == "assistant" else {}

    return ParsedMessage(
        role=role,
        timestamp=timestamp,
        content_json=raw,
        model=extras.get("model") if isinstance(extras.get("model"), str) else None,  # type: ignore[arg-type]
        input_tokens=_int_or_none(extras.get("input_tokens")),
        output_tokens=_int_or_none(extras.get("output_tokens")),
        cache_creation_input_tokens=_int_or_none(extras.get("cache_creation_input_tokens")),
        cache_read_input_tokens=_int_or_none(extras.get("cache_read_input_tokens")),
    )


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
