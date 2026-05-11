"""Tests for csm.identity (V2.A2 title / agent_kind / nickname)."""

from __future__ import annotations

from csm.identity import (
    AGENT_KINDS,
    TITLE_MAX_LEN,
    derive_title_from_user_prompt,
    generate_nickname,
    infer_agent_kind,
)

# ────────── derive_title_from_user_prompt ──────────


def test_title_short_prompt_returned_verbatim() -> None:
    assert derive_title_from_user_prompt("debug the failing test in foo_test.py") == (
        "debug the failing test in foo_test.py"
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
    assert derive_title_from_user_prompt(raw) == "refactor this code"


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
    assert title == "ship it"
    assert not (title or "").endswith("…")


def test_title_takes_first_nonblank_line_only() -> None:
    raw = "fix the foo bug\n\nDetails: ..."
    assert derive_title_from_user_prompt(raw) == "fix the foo bug"


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
    res = infer_agent_kind(
        {"description": "Design the implementation plan for the v2 release"}
    )
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
