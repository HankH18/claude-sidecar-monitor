"""Tests for jsonl.parser."""

from __future__ import annotations

import json

import pytest

from csm.jsonl.parser import ParseError, parse_line


def test_parse_user_message() -> None:
    line = json.dumps(
        {
            "type": "user",
            "message": {"role": "user", "content": "hello"},
            "timestamp": "2026-05-10T00:00:00Z",
        }
    )
    p = parse_line(line)
    assert p.role == "user"
    assert p.timestamp == "2026-05-10T00:00:00Z"
    assert p.input_tokens is None
    assert p.model is None


def test_parse_assistant_message_with_usage() -> None:
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 300,
                    "cache_read_input_tokens": 400,
                },
                "content": [{"type": "text", "text": "ok"}],
            },
            "timestamp": "2026-05-10T00:01:00Z",
        }
    )
    p = parse_line(line)
    assert p.role == "assistant"
    assert p.model == "claude-opus-4-7"
    assert p.input_tokens == 100
    assert p.output_tokens == 200
    assert p.cache_creation_input_tokens == 300
    assert p.cache_read_input_tokens == 400


def test_parse_handles_missing_timestamp() -> None:
    line = json.dumps({"type": "user", "message": {"role": "user", "content": "x"}})
    p = parse_line(line)
    # Falls back to ingest time — just check it's an ISO-shaped string.
    assert "T" in p.timestamp and p.timestamp.endswith("Z")


def test_parse_falls_back_to_message_role_when_type_missing() -> None:
    line = json.dumps({"message": {"role": "user", "content": "x"}})
    p = parse_line(line)
    assert p.role == "user"


def test_parse_unknown_role() -> None:
    line = json.dumps({"some": "shape", "with": "no role"})
    p = parse_line(line)
    assert p.role == "unknown"


def test_parse_empty_line_raises() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_line("")


def test_parse_non_json_raises() -> None:
    with pytest.raises(ParseError, match="invalid JSON"):
        parse_line("not json at all")


def test_parse_array_top_level_raises() -> None:
    with pytest.raises(ParseError, match="expected object"):
        parse_line(json.dumps([1, 2, 3]))


def test_parse_assistant_without_usage_returns_nones() -> None:
    line = json.dumps(
        {
            "type": "assistant",
            "message": {"role": "assistant", "model": "claude-x", "content": []},
            "timestamp": "2026-05-10T00:00:00Z",
        }
    )
    p = parse_line(line)
    assert p.model == "claude-x"
    assert p.input_tokens is None
    assert p.output_tokens is None
