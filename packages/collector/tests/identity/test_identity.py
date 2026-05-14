"""Tests for csm.identity (V2.A2 title / agent_kind / nickname)."""

from __future__ import annotations

import json

from csm.identity import (
    AGENT_KINDS,
    TITLE_MAX_LEN,
    derive_title_from_user_prompt,
    generate_nickname,
    infer_agent_kind,
)

# ────────── derive_title_from_user_prompt ──────────


def test_title_short_prompt_returned_capitalised() -> None:
    # V2 titles sentence-case the first letter so the dashboard reads
    # like English rather than command-line dictation.
    assert derive_title_from_user_prompt("debug the failing test in foo_test.py") == (
        "Debug the failing test in foo_test.py"
    )


def test_title_empty_or_whitespace_returns_none() -> None:
    assert derive_title_from_user_prompt("") is None
    assert derive_title_from_user_prompt("   \n\n  ") is None
    assert derive_title_from_user_prompt(None) is None


def test_title_strips_claude_code_slash_command_wrappers() -> None:
    """The harness injects <command-message>/<command-name>/<command-args>
    tags around slash commands. The actual user intent follows after."""
    raw = (
        "<command-message>plan</command-message>\n"
        "<command-name>/plan</command-name>\n"
        "<command-args>Build a great dashboard</command-args>\n"
        "Build a great dashboard"
    )
    assert derive_title_from_user_prompt(raw) == "Build a great dashboard"


def test_title_strips_leading_markdown_punctuation() -> None:
    raw = "  # Goal: ship the v2 release tomorrow"
    title = derive_title_from_user_prompt(raw)
    assert title is not None
    assert title.startswith("Goal:")


def test_title_strips_leading_code_fence() -> None:
    raw = "```python\nrefactor this code"
    assert derive_title_from_user_prompt(raw) == "Refactor this code"


def test_title_truncates_long_prompts_at_word_boundary() -> None:
    raw = "Refactor " + ("a-very-long-word " * 20)
    title = derive_title_from_user_prompt(raw)
    assert title is not None
    assert len(title) <= TITLE_MAX_LEN
    assert title.endswith("…")
    # Cut at a word boundary, not mid-word.
    assert not title[:-1].rstrip().endswith("-")


def test_title_short_enough_no_ellipsis() -> None:
    title = derive_title_from_user_prompt("ship it")
    assert title == "Ship it"
    assert not (title or "").endswith("…")


def test_title_takes_first_nonblank_line_only() -> None:
    raw = "fix the foo bug\n\nDetails: ..."
    assert derive_title_from_user_prompt(raw) == "Fix the foo bug"


def test_title_skips_tool_result_continuation_prefixes() -> None:
    assert derive_title_from_user_prompt("[Continuing from prior turn]") is None
    assert derive_title_from_user_prompt("[Tool result] ...") is None
    assert derive_title_from_user_prompt("[System reminder]") is None


def test_title_unicode_word_boundary() -> None:
    # Ensure non-ASCII characters don't break the truncation.
    raw = "Refactor " + ("résumé " * 30)
    title = derive_title_from_user_prompt(raw)
    assert title is not None
    assert len(title) <= TITLE_MAX_LEN


# ────────── V3 title v2: slash command stripping, first sentence, markdown ──────────


def test_title_strips_leading_slash_command() -> None:
    assert derive_title_from_user_prompt("/plan take a look at the auth module") == (
        "Take a look at the auth module"
    )


def test_title_strips_slash_command_with_hyphenated_name() -> None:
    assert derive_title_from_user_prompt("/code-review the new permissions module") == (
        "The new permissions module"
    )


def test_title_preserves_bare_slash_command_when_no_args() -> None:
    """`/help` with no arguments — keep the command name so the title isn't blank."""
    assert derive_title_from_user_prompt("/help") == "/help"


def test_title_takes_first_sentence_not_first_80_chars() -> None:
    raw = (
        "Build a permissions API. It needs to support bearer auth, "
        "with HMAC signing for deep links."
    )
    assert derive_title_from_user_prompt(raw) == "Build a permissions API."


def test_title_falls_back_to_word_boundary_when_no_sentence_break() -> None:
    raw = "This is a long unterminated prompt that just keeps going without any period " + (
        "or other terminator " * 5
    )
    title = derive_title_from_user_prompt(raw)
    assert title is not None
    assert len(title) <= TITLE_MAX_LEN
    assert title.endswith("…")


def test_title_strips_inline_markdown_emphasis() -> None:
    raw = "**Critical**: fix the *broken* `auth` flow"
    assert derive_title_from_user_prompt(raw) == "Critical: fix the broken auth flow"


def test_title_collapses_internal_whitespace() -> None:
    raw = "Fix    the    foo    bug"
    assert derive_title_from_user_prompt(raw) == "Fix the foo bug"


def test_title_preserves_path_leading_no_capitalisation() -> None:
    """Don't capitalise `/path/to/file.ts` — it'd look broken."""
    assert derive_title_from_user_prompt("/path/to/file.ts changes") == ("/path/to/file.ts changes")


def test_title_real_world_examples() -> None:
    """Regression: the actual messy prompts the user complained about."""
    # The "doesn't seem like much has changed" prompt — long, ends mid-word.
    raw = "It doesn't seem like much has changed since the last version."
    assert derive_title_from_user_prompt(raw) == raw

    # A slash-command + bullet — old behaviour returned `/plan take a look...`,
    # new behaviour drops the slash command AND capitalises.
    raw = "/plan take a look at this project and generally see what can be improved"
    title = derive_title_from_user_prompt(raw)
    assert title is not None
    assert not title.startswith("/plan")
    assert title.startswith("Take")


# ────────── infer_agent_kind ──────────


def test_kind_from_subagent_type_general_purpose() -> None:
    res = infer_agent_kind({"subagent_type": "general-purpose"})
    assert res is not None
    assert res.kind == "general"
    assert res.confidence >= 0.9


def test_kind_from_subagent_type_explore() -> None:
    res = infer_agent_kind({"subagent_type": "Explore"})
    assert res is not None
    assert res.kind == "explorer"


def test_kind_from_subagent_type_code_reviewer() -> None:
    res = infer_agent_kind({"subagent_type": "code-reviewer"})
    assert res is not None
    assert res.kind == "reviewer"
    assert res.confidence == 0.95


def test_kind_from_prompt_regex_reviewer() -> None:
    res = infer_agent_kind({"prompt": "You're an auditor. Review the diff for..."})
    assert res is not None
    assert res.kind == "reviewer"
    assert 0.6 <= res.confidence < 0.95


def test_kind_from_prompt_regex_planner() -> None:
    res = infer_agent_kind({"description": "Design the implementation plan for the v2 release"})
    assert res is not None
    assert res.kind == "planner"


def test_kind_subagent_type_wins_over_prompt() -> None:
    """Explicit subagent_type is high-confidence; the prompt heuristic
    must not override it."""
    res = infer_agent_kind(
        {
            "subagent_type": "general-purpose",
            "prompt": "You're an auditor reviewing all the code.",
        }
    )
    assert res is not None
    assert res.kind == "general"  # NOT "reviewer"


def test_kind_model_fallback_only_when_no_subagent_signal() -> None:
    res = infer_agent_kind(model="claude-opus-4-7")
    assert res is not None
    assert res.kind == "planner"
    assert res.confidence < 0.5


def test_kind_returns_none_when_no_signal() -> None:
    assert infer_agent_kind() is None
    assert infer_agent_kind({}) is None
    assert infer_agent_kind({"unknown": "value"}) is None


def test_kind_all_results_are_canonical_labels() -> None:
    """Every kind we ever emit must be in the AGENT_KINDS set so the UI
    icon switch is exhaustive."""
    samples = [
        {"subagent_type": "general-purpose"},
        {"subagent_type": "Explore"},
        {"subagent_type": "Plan"},
        {"subagent_type": "code-reviewer"},
        {"subagent_type": "debugger"},
        {"subagent_type": "test-runner"},
        {"prompt": "You're a debugger. Fix this."},
        {"prompt": "Review the code for correctness."},
        {"description": "Design the implementation plan"},
    ]
    for s in samples:
        res = infer_agent_kind(s)
        assert res is not None, f"no kind for {s}"
        assert res.kind in AGENT_KINDS, f"unknown kind {res.kind!r} for {s}"


# ────────── generate_nickname ──────────


def test_nickname_is_deterministic_per_session_id() -> None:
    sid = "02b11697-32c9-467e-ab4a-9858e7570c8d"
    assert generate_nickname(sid) == generate_nickname(sid)


def test_nickname_format() -> None:
    import re

    pattern = re.compile(r"^[a-z]+-[a-z]+-\d{4}$")
    for sid in (
        "02b11697-32c9-467e-ab4a-9858e7570c8d",
        "deadbeef",
        "abc",
        "x",
        "",
    ):
        nick = generate_nickname(sid)
        assert pattern.match(nick), f"bad format: {nick!r}"


def test_nickname_low_collision_rate_on_10k_uuids() -> None:
    """A modest collision check — across 10,000 random-looking UUIDs we
    expect well under 1% duplicates (real users have <10k sessions in
    their lifetime). This isn't a security guarantee, just a sanity gate
    on the word-list size + hash distribution."""
    import secrets

    names = {generate_nickname(secrets.token_hex(16)) for _ in range(10_000)}
    # ~3.3M total namespace; collisions at 10k samples follow ~birthday-paradox
    # math: ~15 expected. Allow generous slack for run-to-run variance.
    assert len(names) >= 9950, f"too many collisions: {10_000 - len(names)}"


# ────────── backfill_titles ──────────


def test_backfill_titles_rederives_from_earliest_user_prompt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """V3 — the startup backfill re-derives titles for every session
    whose title_source='user_prompt' using the current heuristic.
    Lets improvements to derive_title_from_user_prompt propagate to
    sessions ingested before the heuristic was updated.
    """
    from csm.db import connect
    from csm.identity import backfill_titles

    conn = connect(db_path=tmp_path / "store.db")
    try:
        # Seed two sessions with stale (lowercase) titles that the
        # current heuristic would sentence-case.
        for sid, stale_title, prompt in [
            ("s-alpha", "ship it", "ship it"),
            ("s-beta", "/plan refactor auth", "/plan refactor auth"),
        ]:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, worktree_root, cwd, state, last_event_at,
                    started_at, title, title_source
                ) VALUES (?, ?, ?, 'done', '2026-05-10T00:00:00Z',
                          '2026-05-10T00:00:00Z', ?, 'user_prompt')
                """,
                (sid, "/tmp/p", "/tmp/p", stale_title),
            )
            conn.execute(
                "INSERT INTO events(session_id, event_name, received_at, payload_json) "
                "VALUES (?, 'UserPromptSubmit', '2026-05-10T00:00:00Z', ?)",
                (sid, json.dumps({"prompt": prompt})),
            )

        # Session with a user-set title (title_source != 'user_prompt')
        # — backfill MUST NOT touch it.
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, worktree_root, cwd, state, last_event_at,
                started_at, title, title_source
            ) VALUES ('s-pinned', '/tmp/p', '/tmp/p', 'done',
                      '2026-05-10T00:00:00Z', '2026-05-10T00:00:00Z',
                      'do not touch', 'user_set')
            """
        )

        changed = backfill_titles(conn)
        assert changed == 2

        titles = dict(
            conn.execute(
                "SELECT session_id, title FROM sessions WHERE session_id LIKE 's-%'"
            ).fetchall()
        )
        assert titles["s-alpha"] == "Ship it"
        assert titles["s-beta"] == "Refactor auth"  # /plan stripped, sentence-cased
        assert titles["s-pinned"] == "do not touch"
    finally:
        conn.close()


def test_backfill_titles_is_idempotent_when_already_current(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A second backfill call after the first changes nothing."""
    from csm.db import connect
    from csm.identity import backfill_titles

    conn = connect(db_path=tmp_path / "store.db")
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, worktree_root, cwd, state, last_event_at,
                started_at, title, title_source
            ) VALUES ('s-1', '/tmp/p', '/tmp/p', 'done',
                      '2026-05-10T00:00:00Z', '2026-05-10T00:00:00Z',
                      'old', 'user_prompt')
            """
        )
        conn.execute(
            "INSERT INTO events(session_id, event_name, received_at, payload_json) "
            "VALUES ('s-1', 'UserPromptSubmit', '2026-05-10T00:00:00Z', ?)",
            (json.dumps({"prompt": "fix the foo bug"}),),
        )
        assert backfill_titles(conn) == 1
        assert backfill_titles(conn) == 0
    finally:
        conn.close()


def test_backfill_titles_skips_sessions_without_user_prompt_event(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """If the source UserPromptSubmit event was purged or never ingested,
    leave the existing title alone — better stale than blank."""
    from csm.db import connect
    from csm.identity import backfill_titles

    conn = connect(db_path=tmp_path / "store.db")
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, worktree_root, cwd, state, last_event_at,
                started_at, title, title_source
            ) VALUES ('s-orphan', '/tmp/p', '/tmp/p', 'done',
                      '2026-05-10T00:00:00Z', '2026-05-10T00:00:00Z',
                      'kept', 'user_prompt')
            """
        )
        assert backfill_titles(conn) == 0
        title = conn.execute("SELECT title FROM sessions WHERE session_id = 's-orphan'").fetchone()[
            0
        ]
        assert title == "kept"
    finally:
        conn.close()
