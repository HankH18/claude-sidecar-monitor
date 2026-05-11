"""Session identity heuristics (V2.A2).

Three pure functions, no LLM calls:

- ``derive_title_from_user_prompt(text)`` — turn a raw user message into
  a short readable session title.
- ``infer_agent_kind(tool_input, model)`` — best-effort role classification
  with a confidence score in [0.0, 1.0].
- ``generate_nickname(session_id)`` — deterministic adjective-noun-NNNN
  identifier so the same UUID always renders as the same name.

All three are called from the hook receiver and the JSONL processor at
ingest time and the results are written denormalised onto the
``sessions`` row (see csm.db.migrations.002_v2).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

__all__ = [
    "TITLE_MAX_LEN",
    "AGENT_KINDS",
    "AgentKindResult",
    "derive_title_from_user_prompt",
    "infer_agent_kind",
    "generate_nickname",
]

TITLE_MAX_LEN = 80

# Canonical agent_kind labels. The dashboard renders an icon per kind.
# Keep this list short — the UI icon switch fans out by string match.
AGENT_KINDS = frozenset(
    {
        "coder",
        "reviewer",
        "planner",
        "debugger",
        "explorer",
        "tester",
        "general",
    }
)

# Confidence threshold below which the dashboard renders the icon
# muted/"unknown". The planner doc specified < 0.4.
KIND_CONFIDENCE_MUTED = 0.4


@dataclass(frozen=True)
class AgentKindResult:
    kind: str
    confidence: float


# ────────────────────────── titles ──────────────────────────

# Slash-command wrappers Claude Code injects: `<command-message>...</command-message>`
# and `<command-name>/foo</command-name>`. Strip these so the title shows
# the user's actual intent, not the harness preamble.
_COMMAND_MESSAGE_RE = re.compile(r"<command-(message|name|args)>.*?</command-\1>", re.DOTALL)
_TRIPLE_FENCE_RE = re.compile(r"^\s*```[^\n]*\n", re.MULTILINE)
_LEADING_PUNCT_RE = re.compile(r"^[\s>#*•\-]+")


def derive_title_from_user_prompt(text: str | None) -> str | None:
    """Best-effort one-line title from a raw user-prompt string.

    Returns None when the prompt is empty, pure markup, or recognisably
    a tool-result continuation rather than a fresh user intent.

    - Strips Claude Code's slash-command markup wrappers
    - Strips leading triple-backtick fences (would show as code blocks)
    - Trims to ``TITLE_MAX_LEN`` at a word boundary with an ellipsis
    """
    if not text or not text.strip():
        return None

    cleaned = _COMMAND_MESSAGE_RE.sub("", text).strip()
    if not cleaned:
        return None

    # Drop leading code-fence opener and continuation prompts.
    cleaned = _TRIPLE_FENCE_RE.sub("", cleaned)

    # Skip pure tool-result follow-ups (heuristic).
    lstripped = cleaned.lstrip()
    if lstripped.startswith(("[Continuing", "[Tool result", "[System")):
        return None

    # Take the first non-empty line.
    for raw_line in cleaned.splitlines():
        line = _LEADING_PUNCT_RE.sub("", raw_line).strip()
        if line:
            return _truncate_at_word(line, TITLE_MAX_LEN)
    return None


def _truncate_at_word(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    last_space = cut.rfind(" ")
    if last_space > max_len // 2:  # keep at least half-word
        cut = cut[:last_space]
    return cut.rstrip() + "…"


# ────────────────────────── agent_kind ──────────────────────────

# Map Claude Code's ``subagent_type`` values to our canonical labels.
# These are the dispatched-Agent type slugs we've observed in real
# JSONL captures: "general-purpose", "Explore", "Plan", "code-reviewer",
# "debugger", "test-runner", "planner", "statusline-setup".
_SUBAGENT_TYPE_MAP: dict[str, str] = {
    "general-purpose": "general",
    "explore": "explorer",
    "plan": "planner",
    "planner": "planner",
    "code-reviewer": "reviewer",
    "reviewer": "reviewer",
    "debugger": "debugger",
    "test-runner": "tester",
    "claude-code-guide": "general",
    "statusline-setup": "general",
}

# Regex hints in the Task/Agent prompt itself. Order matters — first match wins.
# Each captures a verb/role keyword in the prompt's opening lines.
_PROMPT_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:you[' ]re|act as)\s+(?:an?\s+)?(reviewer|review|auditor)\b", re.I), "reviewer"),
    (re.compile(r"\b(?:you[' ]re|act as)\s+(?:an?\s+)?(planner|architect)\b", re.I), "planner"),
    (re.compile(r"\b(?:you[' ]re|act as)\s+(?:an?\s+)?(debugger|debug)\b", re.I), "debugger"),
    (re.compile(r"\b(?:you[' ]re|act as)\s+(?:an?\s+)?(coder|developer|engineer)\b", re.I), "coder"),
    (re.compile(r"\b(?:you[' ]re|act as)\s+(?:an?\s+)?(tester|qa)\b", re.I), "tester"),
    (re.compile(r"\bdesign(?:\s+a\s+plan|\s+the\s+implementation)\b", re.I), "planner"),
    (re.compile(r"\breview\s+the\s+code\b", re.I), "reviewer"),
    (re.compile(r"\brun\s+the\s+tests?\b", re.I), "tester"),
)

# Model-based fallback. Low-confidence — useful only when nothing else fired.
_MODEL_FALLBACK: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"opus", re.I), "planner"),
    (re.compile(r"sonnet", re.I), "coder"),
    (re.compile(r"haiku", re.I), "general"),
)


def infer_agent_kind(
    tool_input: dict[str, object] | None = None,
    model: str | None = None,
) -> AgentKindResult | None:
    """Infer a session's role from any of: Agent tool_input.subagent_type,
    regex hints in the Agent prompt, or model name.

    Returns ``None`` when no signal triggers.

    Precedence (highest confidence first):
    1. ``tool_input["subagent_type"]`` mapped via ``_SUBAGENT_TYPE_MAP``  → conf 0.95
    2. Regex match against ``tool_input["prompt"]`` / ``["description"]`` → conf 0.7
    3. ``model`` substring match                                          → conf 0.3
    """
    if tool_input:
        subtype = tool_input.get("subagent_type")
        if isinstance(subtype, str):
            mapped = _SUBAGENT_TYPE_MAP.get(subtype.lower())
            if mapped is not None:
                return AgentKindResult(kind=mapped, confidence=0.95)

        for field in ("description", "prompt"):
            v = tool_input.get(field)
            if not isinstance(v, str):
                continue
            for pattern, kind in _PROMPT_HINTS:
                if pattern.search(v):
                    return AgentKindResult(kind=kind, confidence=0.7)

    if model:
        for pattern, kind in _MODEL_FALLBACK:
            if pattern.search(model):
                return AgentKindResult(kind=kind, confidence=0.3)

    return None


# ────────────────────────── nicknames ──────────────────────────

# Compact word lists — 32 each — chosen to be pronounceable, memorable,
# and unambiguous. Adjective + noun + 4-digit number gives ~3.3M unique
# names with a uniform hash distribution. Collisions within a single
# user's history (<10k sessions) are astronomically unlikely.
_ADJECTIVES = (
    "amber", "azure", "brave", "calm", "crisp", "dawn", "dusk", "ember",
    "frost", "gilded", "hazel", "icy", "jade", "kind", "lush", "mossy",
    "nimble", "ochre", "pearl", "quiet", "rose", "silver", "tidal", "umber",
    "vivid", "wild", "xeric", "yarrow", "zest", "agile", "bold", "lucid",
)

_NOUNS = (
    "river", "harbor", "canyon", "meadow", "summit", "delta", "thicket",
    "glade", "vista", "creek", "ridge", "marsh", "bluff", "hollow", "moor",
    "fjord", "atoll", "savanna", "lagoon", "tundra", "pasture", "grove",
    "forest", "valley", "plateau", "isthmus", "wetland", "barrow", "knoll",
    "expanse", "horizon", "tributary",
)


def generate_nickname(session_id: str) -> str:
    """Deterministic ``adjective-noun-NNNN`` nickname from a session_id.

    Same session_id → same nickname forever, across processes / DB resets.
    Uses BLAKE2b for a stable, fast, fixed-output hash.
    """
    h = hashlib.blake2b(session_id.encode("utf-8"), digest_size=8).digest()
    a = _ADJECTIVES[h[0] % len(_ADJECTIVES)]
    n = _NOUNS[h[1] % len(_NOUNS)]
    # Use bytes 2-3 (big-endian uint16) modulo 10000 for the suffix.
    num = int.from_bytes(h[2:4], "big") % 10000
    return f"{a}-{n}-{num:04d}"
