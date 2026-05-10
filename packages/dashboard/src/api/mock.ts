/**
 * In-process mock data provider used while the collector backend is in flight.
 *
 * Toggled by `useMock` (see ./mode.ts). When mock=true, the use* hooks read
 * from this module and `mockStream()` simulates the SSE event source by
 * firing periodic `session_update` events on a setInterval timer.
 *
 * Numbers below are absolute counts only — no plan ceilings, no projections.
 */

import type {
  ModelTokens,
  Session,
  Settings,
  StreamEvent,
  TokensResponse,
  TreeNode,
} from "./types";

// ---- Sessions ---------------------------------------------------------------

const now = Date.now();
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();

// Two projects:
//   /Users/hank/code/sidecar      (4 sessions, including a tree)
//   /Users/hank/code/widget       (2 sessions)
const PROJECT_A = "/Users/hank/code/sidecar";
const PROJECT_B = "/Users/hank/code/widget";

export const mockSessions: Session[] = [
  // Project A — parent (running, top-level)
  {
    session_id: "a-parent-001",
    parent_session_id: null,
    worktree_root: PROJECT_A,
    project_label: "sidecar",
    cwd: PROJECT_A,
    agent_type: "coordinator",
    state: "running",
    last_event_at: iso(-3000),
    last_event_name: "PostToolUse",
    last_tool_name: null,
    started_at: iso(-1000 * 60 * 12),
    completed_at: null,
    primary_model: "claude-opus-4-7",
    input_tokens: 12_400,
    output_tokens: 5_200,
    cache_read_tokens: 88_000,
    cache_write_tokens: 6_400,
  },
  // Project A — child 1 of parent (in tool, running)
  {
    session_id: "a-child-002",
    parent_session_id: "a-parent-001",
    worktree_root: PROJECT_A,
    project_label: "sidecar",
    cwd: PROJECT_A,
    agent_type: "implementor",
    state: "tool",
    last_event_at: iso(-1500),
    last_event_name: "PreToolUse",
    last_tool_name: "Edit",
    started_at: iso(-1000 * 60 * 8),
    completed_at: null,
    primary_model: "claude-sonnet-4-5",
    input_tokens: 8_100,
    output_tokens: 3_400,
    cache_read_tokens: 41_000,
    cache_write_tokens: 2_300,
  },
  // Project A — child 2 of parent (waiting_user)
  {
    session_id: "a-child-003",
    parent_session_id: "a-parent-001",
    worktree_root: PROJECT_A,
    project_label: "sidecar",
    cwd: PROJECT_A,
    agent_type: "verifier",
    state: "waiting_user",
    last_event_at: iso(-22_000),
    last_event_name: "Notification",
    last_tool_name: null,
    started_at: iso(-1000 * 60 * 6),
    completed_at: null,
    primary_model: "claude-sonnet-4-5",
    input_tokens: 4_500,
    output_tokens: 1_800,
    cache_read_tokens: 18_000,
    cache_write_tokens: 900,
  },
  // Project A — orphan, hung
  {
    session_id: "a-orphan-004",
    parent_session_id: null,
    worktree_root: PROJECT_A,
    project_label: "sidecar",
    cwd: PROJECT_A,
    agent_type: "subagent",
    state: "hung",
    last_event_at: iso(-1000 * 60 * 5),
    last_event_name: "PreToolUse",
    last_tool_name: "Bash",
    started_at: iso(-1000 * 60 * 9),
    completed_at: null,
    primary_model: "claude-sonnet-4-5",
    input_tokens: 2_100,
    output_tokens: 600,
    cache_read_tokens: 8_000,
    cache_write_tokens: 400,
  },
  // Project B — running, top-level
  {
    session_id: "b-running-005",
    parent_session_id: null,
    worktree_root: PROJECT_B,
    project_label: "widget",
    cwd: PROJECT_B,
    agent_type: "coordinator",
    state: "running",
    last_event_at: iso(-2000),
    last_event_name: "PostToolUse",
    last_tool_name: null,
    started_at: iso(-1000 * 60 * 3),
    completed_at: null,
    primary_model: "claude-opus-4-7",
    input_tokens: 3_300,
    output_tokens: 1_100,
    cache_read_tokens: 12_000,
    cache_write_tokens: 700,
  },
  // Project B — done
  {
    session_id: "b-done-006",
    parent_session_id: null,
    worktree_root: PROJECT_B,
    project_label: "widget",
    cwd: PROJECT_B,
    agent_type: "implementor",
    state: "done",
    last_event_at: iso(-1000 * 60 * 2),
    last_event_name: "Stop",
    last_tool_name: null,
    started_at: iso(-1000 * 60 * 22),
    completed_at: iso(-1000 * 60 * 2),
    primary_model: "claude-sonnet-4-5",
    input_tokens: 16_400,
    output_tokens: 7_800,
    cache_read_tokens: 96_000,
    cache_write_tokens: 5_500,
  },
];

// ---- Tree -------------------------------------------------------------------

function sessionById(id: string): Session {
  const s = mockSessions.find((x) => x.session_id === id);
  if (!s) throw new Error(`mock: no session ${id}`);
  return s;
}

function buildSubtree(rootId: string): TreeNode {
  const session = sessionById(rootId);
  const children = mockSessions
    .filter((s) => s.parent_session_id === rootId)
    .map((c) => buildSubtree(c.session_id));

  // Roll up self + descendants
  const self = {
    input: session.input_tokens,
    output: session.output_tokens,
    cache_read: session.cache_read_tokens,
    cache_write: session.cache_write_tokens,
  };
  const subtree = children.reduce(
    (acc, c) => ({
      input: acc.input + c.subtree_tokens.input,
      output: acc.output + c.subtree_tokens.output,
      cache_read: acc.cache_read + c.subtree_tokens.cache_read,
      cache_write: acc.cache_write + c.subtree_tokens.cache_write,
      descendant_count: acc.descendant_count + c.subtree_tokens.descendant_count + 1,
    }),
    { ...self, descendant_count: 0 },
  );

  return { session, children, subtree_tokens: subtree };
}

/** Returns a synthetic tree-of-trees for a given worktree_root. */
export function mockTree(worktreeRoot: string): TreeNode {
  const roots = mockSessions.filter(
    (s) => s.worktree_root === worktreeRoot && s.parent_session_id === null,
  );
  if (roots.length === 0) {
    // Empty placeholder — caller should still render.
    const placeholder: Session = {
      session_id: `__empty__:${worktreeRoot}`,
      parent_session_id: null,
      worktree_root: worktreeRoot,
      project_label: worktreeRoot.split("/").pop() ?? worktreeRoot,
      cwd: worktreeRoot,
      agent_type: null,
      state: "done",
      last_event_at: iso(0),
      last_event_name: null,
      last_tool_name: null,
      started_at: iso(0),
      completed_at: iso(0),
      primary_model: null,
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
    };
    return {
      session: placeholder,
      children: [],
      subtree_tokens: {
        input: 0,
        output: 0,
        cache_read: 0,
        cache_write: 0,
        descendant_count: 0,
      },
    };
  }
  if (roots.length === 1) return buildSubtree(roots[0].session_id);

  // Multiple roots — synthesize a virtual project node so callers always get
  // a single TreeNode. Children are the real roots.
  const childTrees = roots.map((r) => buildSubtree(r.session_id));
  const totals = childTrees.reduce(
    (acc, c) => ({
      input: acc.input + c.subtree_tokens.input,
      output: acc.output + c.subtree_tokens.output,
      cache_read: acc.cache_read + c.subtree_tokens.cache_read,
      cache_write: acc.cache_write + c.subtree_tokens.cache_write,
      descendant_count: acc.descendant_count + c.subtree_tokens.descendant_count + 1,
    }),
    { input: 0, output: 0, cache_read: 0, cache_write: 0, descendant_count: 0 },
  );
  const virtualSession: Session = {
    session_id: `__project__:${worktreeRoot}`,
    parent_session_id: null,
    worktree_root: worktreeRoot,
    project_label: roots[0].project_label,
    cwd: worktreeRoot,
    agent_type: "project",
    state: "running",
    last_event_at: iso(0),
    last_event_name: null,
    last_tool_name: null,
    started_at:
      roots
        .map((r) => r.started_at)
        .sort()
        .at(0) ?? iso(0),
    completed_at: null,
    primary_model: null,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
  };
  return { session: virtualSession, children: childTrees, subtree_tokens: totals };
}

// ---- Tokens -----------------------------------------------------------------

function modelTotals(): ModelTokens[] {
  const by: Record<string, ModelTokens> = {};
  for (const s of mockSessions) {
    const m = s.primary_model ?? "unknown";
    if (!by[m]) by[m] = { model: m, input: 0, output: 0, cache_read: 0, cache_write: 0 };
    by[m].input += s.input_tokens;
    by[m].output += s.output_tokens;
    by[m].cache_read += s.cache_read_tokens;
    by[m].cache_write += s.cache_write_tokens;
  }
  return Object.values(by).sort((a, b) => b.input + b.output - (a.input + a.output));
}

function dailyTotals(): TokensResponse["dailyTotals"] {
  // 14 days, 2 models per day with deterministic-ish synthetic numbers.
  const out: TokensResponse["dailyTotals"] = [];
  const day = 1000 * 60 * 60 * 24;
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now - i * day).toISOString().slice(0, 10);
    // simple wave so the bar chart isn't flat
    const k = (14 - i) * 1000;
    out.push({
      date: d,
      model: "claude-opus-4-7",
      input: k * 1.3,
      output: k * 0.6,
      cache_read: k * 4,
      cache_write: k * 0.3,
    });
    out.push({
      date: d,
      model: "claude-sonnet-4-5",
      input: k * 0.8,
      output: k * 0.4,
      cache_read: k * 2.5,
      cache_write: k * 0.2,
    });
  }
  return out;
}

export function mockTokens(): TokensResponse {
  const top = [...mockSessions]
    .sort((a, b) => b.input_tokens + b.output_tokens - (a.input_tokens + a.output_tokens))
    .slice(0, 5)
    .map((s) => ({
      ...s,
      input: s.input_tokens,
      output: s.output_tokens,
      cache_read: s.cache_read_tokens,
      cache_write: s.cache_write_tokens,
    }));

  const byProject: Record<
    string,
    {
      worktree_root: string;
      project_label: string | null;
      input: number;
      output: number;
      cache_read: number;
      cache_write: number;
      session_count: number;
    }
  > = {};
  for (const s of mockSessions) {
    const k = s.worktree_root;
    if (!byProject[k]) {
      byProject[k] = {
        worktree_root: s.worktree_root,
        project_label: s.project_label,
        input: 0,
        output: 0,
        cache_read: 0,
        cache_write: 0,
        session_count: 0,
      };
    }
    byProject[k].input += s.input_tokens;
    byProject[k].output += s.output_tokens;
    byProject[k].cache_read += s.cache_read_tokens;
    byProject[k].cache_write += s.cache_write_tokens;
    byProject[k].session_count += 1;
  }
  const topProjects = Object.values(byProject)
    .map(({ session_count: _ignored, ...rest }) => rest)
    .sort((a, b) => b.input + b.output - (a.input + a.output));
  // Re-attach session_count for UI use (extra field is allowed by the API contract).
  const topProjectsWithCount = topProjects.map((p) => ({
    ...p,
    session_count: byProject[p.worktree_root].session_count,
  }));

  return {
    topSessions: top,
    topProjects: topProjectsWithCount,
    totalsByModel: modelTotals(),
    dailyTotals: dailyTotals(),
  };
}

// ---- Settings ---------------------------------------------------------------

export const mockSettings: Settings = {
  hang_yellow_ms: 60_000,
  hang_red_ms: 180_000,
  ntfy_topic: "csm-hank-demo",
};

// In-memory mutator so the Settings page round-trips PATCH locally.
let mutableSettings: Settings = { ...mockSettings };
export function getMockSettings(): Settings {
  return { ...mutableSettings };
}
export function patchMockSettings(partial: Partial<Settings>): Settings {
  mutableSettings = { ...mutableSettings, ...partial };
  return { ...mutableSettings };
}

// ---- Stream simulator -------------------------------------------------------

interface StreamHandle {
  close(): void;
}

/**
 * Fake EventSource. Periodically picks a running session and emits a
 * `session_update` with bumped tokens + `last_event_at`. Used by useStream
 * when mock=true.
 */
export function mockStream(handler: (e: StreamEvent) => void): StreamHandle {
  const intervalMs = 2500;
  const id = setInterval(() => {
    const live = mockSessions.filter((s) => s.state === "running" || s.state === "tool");
    if (live.length === 0) return;
    const target = live[Math.floor(Math.random() * live.length)];
    target.last_event_at = new Date().toISOString();
    target.input_tokens += 100;
    target.output_tokens += 25;
    target.cache_read_tokens += 800;
    handler({
      kind: "session_update",
      session_id: target.session_id,
      data: {
        session_id: target.session_id,
        state: target.state,
        last_event_at: target.last_event_at,
        input_tokens: target.input_tokens,
        output_tokens: target.output_tokens,
        cache_read_tokens: target.cache_read_tokens,
        cache_write_tokens: target.cache_write_tokens,
      },
    });
  }, intervalMs);
  return {
    close() {
      clearInterval(id);
    },
  };
}

// ---- Transcript fixtures ----------------------------------------------------

export interface TranscriptMessage {
  message_id: number;
  role: "user" | "assistant" | "tool_result" | "system";
  timestamp: string;
  /** Stringified content; UI renders verbatim with monospace where appropriate. */
  content: string;
  model?: string;
  tool_name?: string;
  /** True when content is an Edit/Write diff. */
  is_diff?: boolean;
}

const transcriptsBySession: Record<string, TranscriptMessage[]> = {
  "a-parent-001": [
    {
      message_id: 1,
      role: "user",
      timestamp: iso(-1000 * 60 * 12),
      content: "Add a token badge to the dashboard overview rows.",
    },
    {
      message_id: 2,
      role: "assistant",
      timestamp: iso(-1000 * 60 * 11),
      content:
        "I'll plan this in two steps: extract a TokenBadge component, then wire it into the Overview row.",
      model: "claude-opus-4-7",
    },
    {
      message_id: 3,
      role: "assistant",
      timestamp: iso(-1000 * 60 * 10),
      content: "Edit src/components/TokenBadge.tsx",
      tool_name: "Edit",
      is_diff: true,
      model: "claude-opus-4-7",
    },
    {
      message_id: 4,
      role: "tool_result",
      timestamp: iso(-1000 * 60 * 10 + 500),
      content: "File created: src/components/TokenBadge.tsx (32 lines)",
      tool_name: "Edit",
    },
    {
      message_id: 5,
      role: "assistant",
      timestamp: iso(-1000 * 60 * 9),
      content: "Now I'll run the tests.",
      model: "claude-opus-4-7",
    },
    {
      message_id: 6,
      role: "assistant",
      timestamp: iso(-1000 * 60 * 9 + 1000),
      content: "Bash: bun run test",
      tool_name: "Bash",
    },
    {
      message_id: 7,
      role: "tool_result",
      timestamp: iso(-1000 * 60 * 9 + 5000),
      content: "Test Files  3 passed (3)\n     Tests  9 passed (9)\n  Duration  1.2s",
      tool_name: "Bash",
    },
  ],
  "a-child-002": [
    {
      message_id: 1,
      role: "user",
      timestamp: iso(-1000 * 60 * 8),
      content: "Implement the Edit step.",
    },
    {
      message_id: 2,
      role: "assistant",
      timestamp: iso(-1000 * 60 * 7),
      content: "Editing src/components/TokenBadge.tsx",
      model: "claude-sonnet-4-5",
      tool_name: "Edit",
      is_diff: true,
    },
  ],
};

export function mockTranscript(sessionId: string): TranscriptMessage[] {
  return (
    transcriptsBySession[sessionId] ?? [
      {
        message_id: 1,
        role: "user",
        timestamp: iso(-1000 * 60),
        content: "(no transcript captured for this session yet)",
      },
    ]
  );
}

// ---- Event timeline fixture (PreToolUse / PostToolUse pairs) ----------------

export interface TimelineEntry {
  event_id: number;
  event_name: "PreToolUse" | "PostToolUse" | "UserPromptSubmit" | "Stop";
  tool_name?: string;
  timestamp: string;
  duration_ms?: number;
}

const timelinesBySession: Record<string, TimelineEntry[]> = {
  "a-parent-001": [
    { event_id: 1, event_name: "UserPromptSubmit", timestamp: iso(-1000 * 60 * 12) },
    { event_id: 2, event_name: "PreToolUse", tool_name: "Edit", timestamp: iso(-1000 * 60 * 10) },
    {
      event_id: 3,
      event_name: "PostToolUse",
      tool_name: "Edit",
      timestamp: iso(-1000 * 60 * 10 + 500),
      duration_ms: 480,
    },
    { event_id: 4, event_name: "PreToolUse", tool_name: "Bash", timestamp: iso(-1000 * 60 * 9) },
    {
      event_id: 5,
      event_name: "PostToolUse",
      tool_name: "Bash",
      timestamp: iso(-1000 * 60 * 9 + 5000),
      duration_ms: 4900,
    },
  ],
};

export function mockTimeline(sessionId: string): TimelineEntry[] {
  return timelinesBySession[sessionId] ?? [];
}
