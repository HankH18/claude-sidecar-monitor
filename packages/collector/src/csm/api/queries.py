"""Read-only DB query helpers used by the API routes.

Centralises SQL so route handlers stay focused on shape conversion.
"""

from __future__ import annotations

from typing import Any

from csm.api.models import (
    DailyTotal,
    ModelTokens,
    Session,
    SubtreeTokens,
    TopProject,
    TopSession,
    TranscriptMessage,
    TreeNode,
)
from csm.tokens import get_daily_totals, get_subtree_tokens
from csm.tree import build_project_tree

_SESSION_COLS = (
    "session_id, parent_session_id, worktree_root, project_label, cwd, "
    "transcript_path, agent_type, state, last_event_at, last_event_name, "
    "last_tool_name, started_at, completed_at, primary_model, input_tokens, "
    "output_tokens, cache_read_tokens, cache_write_tokens"
)


def _row_to_session(row: tuple[Any, ...]) -> Session:
    return Session(
        session_id=row[0],
        parent_session_id=row[1],
        worktree_root=row[2],
        project_label=row[3],
        cwd=row[4],
        transcript_path=row[5],
        agent_type=row[6],
        state=row[7],
        last_event_at=row[8],
        last_event_name=row[9],
        last_tool_name=row[10],
        started_at=row[11],
        completed_at=row[12],
        primary_model=row[13],
        input_tokens=row[14],
        output_tokens=row[15],
        cache_read_tokens=row[16],
        cache_write_tokens=row[17],
    )


def list_sessions(conn: Any, *, limit: int = 200) -> list[Session]:
    rows = conn.execute(
        f"SELECT {_SESSION_COLS} FROM sessions ORDER BY last_event_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_session(r) for r in rows]


def get_session(conn: Any, session_id: str) -> Session | None:
    row = conn.execute(
        f"SELECT {_SESSION_COLS} FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row) if row else None


def get_settings_dict(conn: Any) -> dict[str, str]:
    return dict(conn.execute("SELECT key, value FROM settings").fetchall())


def latest_event_at(conn: Any) -> str | None:
    row = conn.execute("SELECT MAX(last_event_at) FROM sessions").fetchone()
    return row[0] if row and row[0] else None


def list_transcript(
    conn: Any, session_id: str, *, after: int | None = None, limit: int = 100
) -> list[TranscriptMessage]:
    if after is None:
        rows = conn.execute(
            """
            SELECT message_id, session_id, role, timestamp, content_json, model,
                   input_tokens, output_tokens,
                   cache_creation_input_tokens, cache_read_input_tokens
            FROM transcript_messages
            WHERE session_id = ?
            ORDER BY message_id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT message_id, session_id, role, timestamp, content_json, model,
                   input_tokens, output_tokens,
                   cache_creation_input_tokens, cache_read_input_tokens
            FROM transcript_messages
            WHERE session_id = ? AND message_id > ?
            ORDER BY message_id ASC
            LIMIT ?
            """,
            (session_id, after, limit),
        ).fetchall()
    return [
        TranscriptMessage(
            message_id=r[0],
            session_id=r[1],
            role=r[2],
            timestamp=r[3],
            content_json=r[4],
            model=r[5],
            input_tokens=r[6],
            output_tokens=r[7],
            cache_creation_input_tokens=r[8],
            cache_read_input_tokens=r[9],
        )
        for r in rows
    ]


def project_tree(conn: Any, worktree_root: str) -> list[TreeNode]:
    """Build a TreeNode-compatible tree (with subtree_tokens) for a project."""
    roots = build_project_tree(conn, worktree_root)
    return [_to_tree_node(conn, r) for r in roots]


def _to_tree_node(conn: Any, node: Any) -> TreeNode:
    children = [_to_tree_node(conn, c) for c in node.children]
    subtree = get_subtree_tokens(conn, node.session_id)
    # The TreeNodeData carries only the columns build_project_tree selected;
    # fetch the full row so consumers get worktree_root / cwd / project_label /
    # parent_session_id / transcript_path / last_event_name — all of which the
    # dashboard's ProjectDetail page links and labels against. The recursive
    # CTE depth is bounded by the agent tree (typically ≤5), so the extra
    # SELECT per node is negligible.
    session = get_session(conn, node.session_id)
    if session is None:
        # Race: the row was deleted between build_project_tree and now.
        # Fall back to the partial info we already have so the tree
        # response is still well-shaped.
        session = Session(
            session_id=node.session_id,
            parent_session_id=None,
            worktree_root="",
            project_label=None,
            cwd="",
            transcript_path=None,
            agent_type=node.agent_type,
            state=node.state,
            last_event_at=node.last_event_at,
            last_event_name=None,
            last_tool_name=node.last_tool_name,
            started_at=node.started_at,
            completed_at=None,
            primary_model=node.primary_model,
            input_tokens=node.input_tokens,
            output_tokens=node.output_tokens,
            cache_read_tokens=node.cache_read_tokens,
            cache_write_tokens=node.cache_write_tokens,
        )
    return TreeNode(
        session=session,
        children=children,
        subtree_tokens=SubtreeTokens(
            input=subtree.input,
            output=subtree.output,
            cache_read=subtree.cache_read,
            cache_write=subtree.cache_write,
            descendant_count=subtree.descendant_count,
        ),
    )


def top_sessions(conn: Any, *, since: str, limit: int = 10) -> list[TopSession]:
    rows = conn.execute(
        f"""
        SELECT {_SESSION_COLS}, (input_tokens + output_tokens) AS total
        FROM sessions
        WHERE last_event_at >= ?
        ORDER BY total DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    return [
        TopSession(
            session_id=r[0],
            project_label=r[3],
            worktree_root=r[2],
            agent_type=r[6],
            primary_model=r[13],
            started_at=r[11],
            input=r[14],
            output=r[15],
            cache_read=r[16],
            cache_write=r[17],
        )
        for r in rows
    ]


def top_projects(conn: Any, *, limit: int = 10) -> list[TopProject]:
    rows = conn.execute(
        """
        SELECT
            worktree_root,
            -- Use MIN(project_label) for deterministic output when sessions
            -- in the same worktree disagree on label (rare: a user moved
            -- cwd between sessions). MAX would be equally arbitrary but
            -- MIN is sortable and reproducible across runs.
            COALESCE(MIN(project_label), worktree_root),
            COUNT(*) AS session_count,
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cache_read_tokens), 0),
            COALESCE(SUM(cache_write_tokens), 0)
        FROM sessions
        WHERE worktree_root != ''
        GROUP BY worktree_root
        ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        TopProject(
            worktree_root=r[0],
            project_label=r[1],
            session_count=int(r[2]),
            input=int(r[3]),
            output=int(r[4]),
            cache_read=int(r[5]),
            cache_write=int(r[6]),
        )
        for r in rows
    ]


def totals_by_model(conn: Any) -> list[ModelTokens]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(model, 'unknown'),
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cache_read_input_tokens), 0),
            COALESCE(SUM(cache_creation_input_tokens), 0)
        FROM transcript_messages
        GROUP BY model
        ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
        """
    ).fetchall()
    return [
        ModelTokens(
            model=str(r[0]),
            input=int(r[1]),
            output=int(r[2]),
            cache_read=int(r[3]),
            cache_write=int(r[4]),
        )
        for r in rows
    ]


def daily_totals(conn: Any, start: str, end: str) -> list[DailyTotal]:
    return [
        DailyTotal(
            date=d.date,
            model=d.model,
            input=d.input,
            output=d.output,
            cache_read=d.cache_read,
            cache_write=d.cache_write,
        )
        for d in get_daily_totals(conn, start, end)
    ]
