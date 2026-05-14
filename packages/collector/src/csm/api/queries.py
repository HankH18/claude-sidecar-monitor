"""Read-only DB query helpers used by the API routes.

Centralises SQL so route handlers stay focused on shape conversion.
"""

from __future__ import annotations

import contextlib
from typing import Any

from csm.api.models import (
    DailyTotal,
    DashboardKpis,
    MinuteBucket,
    ModelTokens,
    Session,
    SessionStateCounts,
    SubtreeTokens,
    TopModelToday,
    TopProject,
    TopSession,
    TranscriptMessage,
    TreeNode,
)
from csm.digest import compute_session_digest
from csm.tokens import get_daily_totals, get_subtree_tokens
from csm.tree import build_project_tree

# V3 — rolling token window. Conservative default; trade-off is between
# "shows recent activity in real time" (small window) and "smooths out
# bursty token spend so you actually see the trend" (large window).
TOKENS_LAST_HOUR_SECONDS = 60 * 60

_SESSION_COLS = (
    "session_id, parent_session_id, worktree_root, project_label, cwd, "
    "transcript_path, agent_type, state, last_event_at, last_event_name, "
    "last_tool_name, started_at, completed_at, primary_model, input_tokens, "
    "output_tokens, cache_read_tokens, cache_write_tokens, "
    # v2.A2 identity columns — appended (don't reorder; _row_to_session
    # uses positional indices)
    "title, title_source, agent_kind, agent_kind_confidence, nickname, "
    "activity_summary, activity_updated_at"
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
        title=row[18],
        title_source=row[19],
        agent_kind=row[20],
        agent_kind_confidence=row[21],
        nickname=row[22],
        activity_summary=row[23],
        activity_updated_at=row[24],
    )


def session_tokens_in_window(
    conn: Any, session_id: str, *, seconds: int = TOKENS_LAST_HOUR_SECONDS
) -> int | None:
    """Sum input + output tokens from `transcript_messages` rows for
    ``session_id`` whose timestamp falls within the last ``seconds``.

    Returns:
      - ``int`` when at least one row exists in the window (may be 0)
      - ``None`` when no rows fall in the window — distinct so the UI
        can show "—" instead of "0" for sessions with no recent activity
    """
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), "
        "  COALESCE(SUM(output_tokens), 0) "
        "FROM transcript_messages "
        "WHERE session_id = ? "
        "  AND timestamp >= datetime('now', ?)",
        (session_id, f"-{seconds} seconds"),
    ).fetchone()
    if row is None or row[0] == 0:
        return None
    return int(row[1]) + int(row[2])


def list_sessions(conn: Any, *, limit: int = 200) -> list[Session]:
    rows = conn.execute(
        f"SELECT {_SESSION_COLS} FROM sessions ORDER BY last_event_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    sessions = [_row_to_session(r) for r in rows]
    # V2.B — overlay the freshly-computed digest on the response
    # WITHOUT writing back to the DB. Persisted writes happen on the
    # state-machine path (_maybe_emit_digest after every event). Doing
    # UPDATEs here caused SQLITE_BUSY contention with the receiver's
    # BEGIN IMMEDIATE write lock and N+1 churn on a hot endpoint.
    for s in sessions:
        try:
            summary, generated_at = compute_session_digest(conn, s.session_id)
        except Exception:
            # Digest is best-effort — never let it 500 the API.
            pass
        else:
            if summary is not None and s.activity_summary != summary:
                s.activity_summary = summary
                s.activity_updated_at = generated_at
        # V3 — rolling 60-min token window, also computed at read time.
        # One indexed lookup per session row; the transcript timestamp
        # column has an index (see migration 001). Same best-effort
        # posture as the digest above.
        with contextlib.suppress(Exception):
            s.tokens_last_hour = session_tokens_in_window(conn, s.session_id)
    return sessions


def get_session(conn: Any, session_id: str) -> Session | None:
    row = conn.execute(
        f"SELECT {_SESSION_COLS} FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    session = _row_to_session(row)
    try:
        summary, generated_at = compute_session_digest(conn, session_id)
    except Exception:
        pass
    else:
        if summary is not None and session.activity_summary != summary:
            session.activity_summary = summary
            session.activity_updated_at = generated_at
    with contextlib.suppress(Exception):
        session.tokens_last_hour = session_tokens_in_window(conn, session_id)
    return session


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

    # v2.C3 — virtual subagent leaf. Build a minimal Session from the
    # TreeNodeData (we don't have a real sessions row to look up) and
    # tag the wrapper so the dashboard can render it distinctively.
    if getattr(node, "is_virtual", False):
        virtual_session = Session(
            session_id=node.session_id,  # equals virtual_id
            parent_session_id=None,
            worktree_root="",
            project_label=None,
            cwd="",
            transcript_path=None,
            agent_type=node.agent_type,
            state=node.state,
            last_event_at=node.last_event_at,
            last_event_name=None,
            last_tool_name=None,
            started_at=node.started_at,
            completed_at=None,
            primary_model=None,
            input_tokens=node.input_tokens,
            output_tokens=node.output_tokens,
            cache_read_tokens=node.cache_read_tokens,
            cache_write_tokens=node.cache_write_tokens,
            title=node.title,
            agent_kind=node.agent_kind,
        )
        return TreeNode(
            session=virtual_session,
            children=children,  # always [] for virtuals in v2 MVP
            subtree_tokens=SubtreeTokens(
                input=node.input_tokens,
                output=node.output_tokens,
                cache_read=node.cache_read_tokens,
                cache_write=node.cache_write_tokens,
                descendant_count=0,
            ),
            is_virtual=True,
            virtual_id=node.virtual_id,
            description=node.description,
        )

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



# ────────────────────────── V3 dashboard KPI rollups ──────────────────────────

# Bucket size for the events-per-minute sparkline. 60 buckets * 1 minute
# = a one-hour strip rendered as ~60 vertical bars on the dashboard.
SPARKLINE_BUCKETS = 60
SPARKLINE_BUCKET_SECONDS = 60


def _state_counts(conn: Any) -> SessionStateCounts:
    rows = conn.execute(
        "SELECT state, COUNT(*) FROM sessions GROUP BY state"
    ).fetchall()
    counts = SessionStateCounts()
    for state, n in rows:
        # Setattr by state name — Pydantic v2 validates on assign.
        if hasattr(counts, state):
            setattr(counts, state, int(n))
    return counts


def _tokens_in_window(conn: Any, *, seconds: int) -> int:
    """Sum input+output tokens across ALL transcript rows within the
    given trailing window. Used for the top-line "today" / "last hour"
    KPI tiles."""
    row = conn.execute(
        "SELECT COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0) "
        "FROM transcript_messages "
        "WHERE timestamp >= datetime('now', ?)",
        (f"-{seconds} seconds",),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _events_per_minute_60m(conn: Any) -> list[MinuteBucket]:
    """60-bucket sparkline of events per minute over the last hour.

    Always returns ``SPARKLINE_BUCKETS`` entries (zero-filled), so the
    UI can render a fixed-width strip without worrying about gaps.
    """
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:00Z', received_at) AS minute,
               COUNT(*) AS n
        FROM events
        WHERE received_at >= datetime('now', ?)
        GROUP BY minute
        """,
        (f"-{SPARKLINE_BUCKETS * SPARKLINE_BUCKET_SECONDS} seconds",),
    ).fetchall()
    counts: dict[str, int] = {str(r[0]): int(r[1]) for r in rows}

    # Build a zero-filled series anchored on "now" rounded down to the
    # minute. Using SQLite for the anchor keeps clock semantics aligned
    # with the bucket keys above.
    anchor_row = conn.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:00Z', 'now')"
    ).fetchone()
    anchor = str(anchor_row[0]) if anchor_row and anchor_row[0] else None
    if anchor is None:
        return []

    out: list[MinuteBucket] = []
    # Walk backwards from anchor in 1-minute steps, prepend so the
    # series reads chronologically left-to-right.
    for i in range(SPARKLINE_BUCKETS - 1, -1, -1):
        row = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:00Z', 'now', ?)",
            (f"-{i} minutes",),
        ).fetchone()
        ts = str(row[0]) if row and row[0] else anchor
        out.append(MinuteBucket(ts=ts, count=counts.get(ts, 0)))
    return out


def _top_models_today(conn: Any) -> list[TopModelToday]:
    """Per-model token totals scoped to the last 24h. Mirrors
    `totals_by_model` but with a time filter so the dashboard reads
    'today' not 'all time'."""
    rows = conn.execute(
        """
        SELECT COALESCE(model, '(unknown)') AS model,
               COALESCE(SUM(input_tokens), 0),
               COALESCE(SUM(output_tokens), 0),
               COALESCE(SUM(cache_read_input_tokens), 0),
               COALESCE(SUM(cache_creation_input_tokens), 0)
        FROM transcript_messages
        WHERE timestamp >= datetime('now', '-1 day')
        GROUP BY model
        ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
        LIMIT 5
        """
    ).fetchall()
    return [
        TopModelToday(
            model=str(r[0]),
            input=int(r[1]),
            output=int(r[2]),
            cache_read=int(r[3]),
            cache_write=int(r[4]),
        )
        for r in rows
    ]


def dashboard_kpis(conn: Any) -> DashboardKpis:
    """Single-query bundle for the V3 KPI landing page.

    Composed of independent SELECTs; total wire size is small and the
    queries are short-lived so we don't bother batching. SSE pushes a
    cheap invalidation on relevant bus events; the dashboard refetches.
    """
    state_counts = _state_counts(conn)
    live_sessions = (
        state_counts.running
        + state_counts.tool
        + state_counts.waiting_user
        + state_counts.idle
        + state_counts.hung
    )
    total_tokens_today = _tokens_in_window(conn, seconds=24 * 60 * 60)
    total_tokens_last_hour = _tokens_in_window(conn, seconds=60 * 60)

    events_row = conn.execute(
        "SELECT COUNT(*) FROM events WHERE received_at >= datetime('now', '-1 hour')"
    ).fetchone()
    events_last_hour = int(events_row[0]) if events_row and events_row[0] is not None else 0

    sparkline = _events_per_minute_60m(conn)
    top_models = _top_models_today(conn)

    as_of_row = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')").fetchone()
    as_of = str(as_of_row[0]) if as_of_row and as_of_row[0] else ""

    return DashboardKpis(
        live_sessions=live_sessions,
        state_counts=state_counts,
        hung_sessions=state_counts.hung,
        total_tokens_today=total_tokens_today,
        total_tokens_last_hour=total_tokens_last_hour,
        events_last_hour=events_last_hour,
        events_per_minute_60m=sparkline,
        top_models_today=top_models,
        as_of=as_of,
    )
