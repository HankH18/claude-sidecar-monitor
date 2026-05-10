// Shapes mirror the Pydantic models on the collector. Keep in sync with
// packages/collector/src/csm/api/*.py response models.

export type SessionState = "idle" | "running" | "tool" | "hung" | "done" | "waiting_user";

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
}

export interface ApiError {
  error: { code: string; message: string };
}

export type StreamEventKind =
  | "session_update"
  | "event"
  | "transcript_message"
  | "hang"
  | "settings_changed";

export interface StreamEvent {
  kind: StreamEventKind;
  session_id?: string;
  data: Record<string, unknown>;
}
