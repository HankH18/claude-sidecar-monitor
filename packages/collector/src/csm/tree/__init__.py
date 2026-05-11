"""Agent tree builder (T10).

Resolves ``parent_session_id`` for sessions spawned via the ``Task``
tool. The heuristic per docs/spec.md §4.4:

1. Worktree grouping is the outermost layer.
2. When parent P emits ``PreToolUse(tool_name="Task")``, queue an open
   match window for P (30 s).
3. A child session whose first hook event arrives within the parent's
   window AND shares ``worktree_root`` is bound:
   ``child.parent_session_id = P.session_id``.
4. Children that don't match a Task call appear at the project level
   (``parent_session_id = NULL``) — they're orphans and the UI
   surfaces them at the project root.

Public surface:

- ``resolve_parent(conn, child_session_id)`` — try to find a parent for
  a child session, persist if found. Idempotent.
- ``build_project_tree(conn, worktree_root)`` — return the full tree
  for a project as a recursive structure with sessions and children.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = [
    "MATCH_WINDOW_SECONDS",
    "TreeNodeData",
    "build_project_tree",
    "resolve_parent",
]

MATCH_WINDOW_SECONDS = 30


@dataclass
class TreeNodeData:
    session_id: str
    state: str
    agent_type: str | None
    last_tool_name: str | None
    last_event_at: str
    started_at: str
    primary_model: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    children: list[TreeNodeData] = field(default_factory=list)
    # v2.C3 — virtual subagent flag + identifying metadata. is_virtual=True
    # nodes do NOT correspond to a real `sessions` row; they're synthesised
    # from `subagent_sessions` for in-session Agent tool calls. The
    # dashboard treats them as leaf-only nodes (no transcript drill-in in
    # v2; v2.1 will filter the parent's transcript by subagent_virtual_id).
    is_virtual: bool = False
    virtual_id: str | None = None
    title: str | None = None
    description: str | None = None
    agent_kind: str | None = None
    subagent_type: str | None = None


def _parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp (with or without trailing Z).

    Returns a timezone-aware datetime in UTC. Naive timestamps (no zone)
    are interpreted as UTC — that matches the convention we use in
    ``utcnow_iso`` and in every SQL timestamp we write — but explicit so
    arithmetic with aware datetimes elsewhere doesn't raise.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _format_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_parent(conn: Any, child_session_id: str) -> str | None:
    """Find and persist a parent for ``child_session_id``.

    Returns the resolved parent's session_id, or ``None`` if no match.
    Idempotent — calling repeatedly on a session that already has a
    parent is a no-op (we don't re-resolve).
    """
    row = conn.execute(
        """
        SELECT worktree_root, started_at, parent_session_id
        FROM sessions WHERE session_id = ?
        """,
        (child_session_id,),
    ).fetchone()
    if row is None:
        return None
    worktree_root, started_at, existing_parent = row
    if existing_parent:
        return str(existing_parent)
    if not worktree_root:
        return None  # can't match without a worktree

    started_dt = _parse_iso(started_at)
    window_start = started_dt - timedelta(seconds=MATCH_WINDOW_SECONDS)

    # Find the most recent Task PreToolUse from a *different* session in
    # the same worktree, within the match window before this session
    # started.
    candidate = conn.execute(
        """
        SELECT e.session_id
        FROM events e
        JOIN sessions s ON s.session_id = e.session_id
        WHERE e.event_name = 'PreToolUse'
          AND e.tool_name  = 'Task'
          AND s.worktree_root = ?
          AND e.session_id != ?
          AND e.received_at <= ?
          AND e.received_at >= ?
        ORDER BY e.received_at DESC
        LIMIT 1
        """,
        (
            worktree_root,
            child_session_id,
            _format_iso(started_dt),
            _format_iso(window_start),
        ),
    ).fetchone()
    if candidate is None:
        return None

    parent_id = str(candidate[0])
    conn.execute(
        "UPDATE sessions SET parent_session_id = ? WHERE session_id = ? "
        "AND parent_session_id IS NULL",
        (parent_id, child_session_id),
    )
    return parent_id


def build_project_tree(conn: Any, worktree_root: str) -> list[TreeNodeData]:
    """Return the project's session tree as nested ``TreeNodeData``.

    Sessions in the worktree with ``parent_session_id IS NULL`` are
    roots; their children attach recursively.
    """
    rows = conn.execute(
        """
        SELECT
            session_id, parent_session_id, state, agent_type,
            last_tool_name, last_event_at, started_at, primary_model,
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        FROM sessions
        WHERE worktree_root = ?
        ORDER BY started_at ASC
        """,
        (worktree_root,),
    ).fetchall()

    node_by_id: dict[str, TreeNodeData] = {}
    children_of: dict[str, list[TreeNodeData]] = {}
    # Precompute the set of session_ids that have a parent so the roots
    # filter runs in O(N) instead of the original O(N²) `next(r for r in
    # rows ...)` scan. With 200 sessions per project the difference is 200
    # iterations vs 40,000.
    has_parent: set[str] = set()

    for r in rows:
        node = TreeNodeData(
            session_id=r[0],
            state=r[2],
            agent_type=r[3],
            last_tool_name=r[4],
            last_event_at=r[5],
            started_at=r[6],
            primary_model=r[7],
            input_tokens=r[8],
            output_tokens=r[9],
            cache_read_tokens=r[10],
            cache_write_tokens=r[11],
        )
        node_by_id[r[0]] = node
        parent = r[1]
        if parent:
            children_of.setdefault(parent, []).append(node)
            has_parent.add(r[0])

    # Wire children into their parent nodes.
    for parent_id, kids in children_of.items():
        parent_node = node_by_id.get(parent_id)
        if parent_node is None:
            continue
        parent_node.children = sorted(kids, key=lambda n: n.started_at)

    # v2.C3 — append virtual subagent rows as children of their parent
    # session. Virtuals are leaf-only in v2 MVP (no transcript drill-in).
    # Token totals stay 0 (per-virtual attribution punted to v2.1).
    virtual_rows = conn.execute(
        """
        SELECT
            sa.virtual_id, sa.parent_session_id, sa.title, sa.description,
            sa.agent_kind, sa.subagent_type, sa.state,
            sa.started_at, sa.completed_at,
            sa.input_tokens, sa.output_tokens,
            sa.cache_read_tokens, sa.cache_write_tokens
        FROM subagent_sessions sa
        JOIN sessions s ON s.session_id = sa.parent_session_id
        WHERE s.worktree_root = ?
        ORDER BY sa.started_at ASC
        """,
        (worktree_root,),
    ).fetchall()
    for vr in virtual_rows:
        parent_id = vr[1]
        parent_node = node_by_id.get(parent_id)
        if parent_node is None:
            continue  # parent isn't in this worktree slice — skip
        virtual_node = TreeNodeData(
            session_id=vr[0],  # virtual_id reused as the tree's node_id
            state=vr[6],
            agent_type=vr[5],  # subagent_type doubles as agent_type
            last_tool_name=None,
            last_event_at=vr[8] or vr[7],
            started_at=vr[7],
            primary_model=None,
            input_tokens=vr[9],
            output_tokens=vr[10],
            cache_read_tokens=vr[11],
            cache_write_tokens=vr[12],
            is_virtual=True,
            virtual_id=vr[0],
            title=vr[2],
            description=vr[3],
            agent_kind=vr[4],
            subagent_type=vr[5],
        )
        parent_node.children = sorted(
            [*parent_node.children, virtual_node], key=lambda n: n.started_at
        )

    roots = [node for sid, node in node_by_id.items() if sid not in has_parent]
    return sorted(roots, key=lambda n: n.started_at)
