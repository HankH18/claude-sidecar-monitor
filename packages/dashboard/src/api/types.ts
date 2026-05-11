// Shapes mirror the Pydantic models on the collector. Keep in sync with
// packages/collector/src/csm/api/*.py response models.

export type SessionState = "idle" | "running" | "tool" | "hung" | "done" | "waiting_user";

/**
 * V2.A — heuristic agent classification. Confidence < KIND_CONFIDENCE_MUTED
 * is rendered with muted styling so a low-confidence guess doesn't shout.
 */
export type AgentKind =
  | "general"
  | "explorer"
  | "reviewer"
  | "planner"
  | "coder"
  | "debugger"
  | "refactorer"
  | "tester";

export const KIND_CONFIDENCE_MUTED = 0.4;

export interface Session {
  session_id: string;
  parent_session_id: string | null;
  worktree_root: string;
  project_label: string | null;
  cwd: string;
  agent_type: string | null;
  state: SessionState;
  last_event_at: string;
  last_event_name: string | null;
  last_tool_name: string | null;
  started_at: string;
  completed_at: string | null;
  primary_model: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  // v2.A3 — session identity (all optional; v1 rows leave these null).
  title?: string | null;
  title_source?: string | null;
  agent_kind?: AgentKind | string | null;
  agent_kind_confidence?: number | null;
  nickname?: string | null;
  // v2.B — activity digest (consumption side; derivation lives in the collector).
  activity_summary?: string | null;
  activity_updated_at?: string | null;
}

export interface ModelTokens {
  model: string;
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
}

export interface SessionDetail extends Session {
  by_model: ModelTokens[];
}

export interface TreeNode {
  session: Session;
  children: TreeNode[];
  subtree_tokens: {
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
    descendant_count: number;
  };
  // v2.C3 — virtual subagent rows synthesised by the backend.
  is_virtual?: boolean;
  virtual_id?: string | null;
  description?: string | null;
}

export interface TokensResponse {
  topSessions: Array<
    Session & { input: number; output: number; cache_read: number; cache_write: number }
  >;
  topProjects: Array<{
    worktree_root: string;
    project_label: string | null;
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
  }>;
  totalsByModel: ModelTokens[];
  dailyTotals: Array<{
    date: string;
    model: string;
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
  }>;
}

export interface Settings {
  hang_yellow_ms: number;
  hang_red_ms: number;
  ntfy_topic: string;
  // V2.D4 — phone permission approval. Optional so older collector builds
  // that haven't been migrated to the extended PATCH still deserialise.
  approval_enabled?: boolean;
  approval_tools?: string;
  approval_timeout_ms?: number;
  dashboard_url?: string;
}

// V2.D — permission approval request shape.
export interface PermissionRequest {
  id: number;
  session_id: string;
  tool_use_id: string | null;
  tool_name: string;
  // tool_input is the parsed JSON from tool_input_json — could be anything.
  tool_input: unknown;
  status: "pending" | "allow" | "deny" | "ask" | "expired" | "timed_out";
  decision_reason: string | null;
  requested_at: string;
  decided_at: string | null;
}

export interface PermissionRequestList {
  requests: PermissionRequest[];
}

export interface ApiError {
  error: { code: string; message: string };
}

export type StreamEventKind =
  | "session_update"
  | "event"
  | "transcript_message"
  | "hang"
  | "settings_changed"
  | "permission_request";

export interface StreamEvent {
  kind: StreamEventKind;
  session_id?: string;
  data: Record<string, unknown>;
}
