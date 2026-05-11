"""Tests for jsonl.processor — the file-tailing logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from csm.db import connect
from csm.jsonl.offsets import get_offset
from csm.jsonl.processor import process_file


@pytest.fixture
def db(tmp_path: Path):
    conn = connect(db_path=tmp_path / "store.db")
    yield conn
    conn.close()


def _line(role: str = "user", **extra) -> str:
    obj: dict[str, object] = {
        "type": role,
        "message": {"role": role, "content": "x"},
        "timestamp": "2026-05-10T00:00:00Z",
    }
    obj.update(extra)
    return json.dumps(obj) + "\n"


def _assistant_line(model: str = "claude-opus-4-7", **usage) -> str:
    return (
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "model": model,
                    "usage": usage,
                    "content": [{"type": "text", "text": "ok"}],
                },
                "timestamp": "2026-05-10T00:00:00Z",
            }
        )
        + "\n"
    )


def test_first_pass_persists_all_lines(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line() + _line() + _line())

    n = process_file(db, f)
    assert n == 3

    rows = db.execute(
        "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("abc-123",)
    ).fetchone()[0]
    assert rows == 3

    # Offset advanced to EOF.
    offset = get_offset(db, f)
    assert offset is not None
    assert offset.byte_offset == f.stat().st_size


def test_second_pass_only_persists_new_lines(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line() + _line())
    n1 = process_file(db, f)
    assert n1 == 2

    # Append more lines.
    with f.open("a") as fh:
        fh.write(_line())
        fh.write(_line())

    n2 = process_file(db, f)
    assert n2 == 2

    total = db.execute(
        "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("abc-123",)
    ).fetchone()[0]
    assert total == 4


def test_partial_line_buffered_until_newline(db, tmp_path: Path) -> None:
    """A trailing line without ``\\n`` should NOT be persisted yet."""
    f = tmp_path / "abc-123.jsonl"
    # No trailing newline on the second entry.
    f.write_text(_line() + json.dumps({"type": "user", "message": {"role": "user"}}))

    n = process_file(db, f)
    # Only the completed first line is persisted.
    assert n == 1

    # Now finish the line.
    with f.open("a") as fh:
        fh.write("\n")
    n2 = process_file(db, f)
    assert n2 == 1


def test_garbage_lines_are_skipped(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line() + "garbage not json\n" + _line())

    n = process_file(db, f)
    assert n == 2  # Two valid lines persist; garbage skipped.

    rows = db.execute(
        "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("abc-123",)
    ).fetchone()[0]
    assert rows == 2


def test_inode_change_triggers_full_re_read(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line() + _line())
    process_file(db, f)
    initial_count = db.execute(
        "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("abc-123",)
    ).fetchone()[0]
    assert initial_count == 2

    # Replace the file (different inode). New content should be re-read
    # from offset 0.
    f.unlink()
    f.write_text(_line() + _line() + _line())
    n = process_file(db, f)
    assert n == 3

    final = db.execute(
        "SELECT count(*) FROM transcript_messages WHERE session_id=?", ("abc-123",)
    ).fetchone()[0]
    assert final == 5  # 2 + 3


def test_file_truncated_resets_offset(db, tmp_path: Path) -> None:
    """If the file shrinks (rare, but possible), reset to 0."""
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line() + _line() + _line())
    process_file(db, f)

    # Truncate to a smaller size, same inode.
    f.write_text(_line())  # one line only
    n = process_file(db, f)
    assert n == 1


def test_missing_file_returns_zero(db, tmp_path: Path) -> None:
    f = tmp_path / "vanished.jsonl"
    n = process_file(db, f)
    assert n == 0


def test_assistant_usage_persisted(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(
        _assistant_line(
            input_tokens=10,
            output_tokens=20,
            cache_creation_input_tokens=30,
            cache_read_input_tokens=40,
        )
    )
    process_file(db, f)
    row = db.execute(
        """
        SELECT model, input_tokens, output_tokens,
               cache_creation_input_tokens, cache_read_input_tokens
        FROM transcript_messages WHERE session_id=?
        """,
        ("abc-123",),
    ).fetchone()
    assert row == ("claude-opus-4-7", 10, 20, 30, 40)


def test_session_row_auto_created(db, tmp_path: Path) -> None:
    """JSONL ingest creates a sessions row if hooks haven't seen the session yet."""
    f = tmp_path / "first-time-001.jsonl"
    f.write_text(_line())
    process_file(db, f)
    row = db.execute(
        "SELECT session_id FROM sessions WHERE session_id=?", ("first-time-001",)
    ).fetchone()
    assert row is not None


def test_offset_stable_across_corrupted_utf8(db, tmp_path: Path) -> None:
    """The byte offset must advance by raw-byte count, not by decoded-text
    re-encoded length. A bad byte that decodes to U+FFFD (3 bytes) would
    cause the offset to drift if we re-encode the text; this test asserts
    we stay aligned to the actual file size.
    """
    f = tmp_path / "abc-123.jsonl"
    good_line = _line().encode("utf-8")
    # Insert one isolated bad byte (0xFF) that decode("utf-8", errors="replace")
    # turns into U+FFFD — would be 3 bytes if re-encoded.
    corrupted = good_line + b"\xff\n" + good_line
    f.write_bytes(corrupted)

    process_file(db, f)
    from csm.jsonl.offsets import get_offset

    offset = get_offset(db, f)
    assert offset is not None
    # Offset must equal the actual file size, not the re-encoded text length.
    assert offset.byte_offset == f.stat().st_size


def test_repeat_call_no_new_content_is_noop(db, tmp_path: Path) -> None:
    f = tmp_path / "abc-123.jsonl"
    f.write_text(_line())
    process_file(db, f)
    n = process_file(db, f)
    assert n == 0
