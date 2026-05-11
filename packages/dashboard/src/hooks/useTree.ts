import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, withRetry } from "../api/client";
import { mockTree } from "../api/mock";
import { useMock } from "../api/mode";
import type { Session, TreeNode } from "../api/types";
import { useStream } from "./useStream";

// A burst of session_update events (e.g. a scanner tick that hangs 10
// sessions at once, or a Stop that fires after many late JSONL writes)
// would otherwise trigger 10 GET /api/tree calls in <1 s. Coalesce to a
// single refetch with a trailing-edge timer.
const REFETCH_DEBOUNCE_MS = 350;

/**
 * Collector returns `list[TreeNode]` (one entry per top-level session in the
 * worktree). The page always wants a single TreeNode, so we collapse:
 *  - 0 roots → null
 *  - 1 root → that node
 *  - n roots → synthesize a virtual `__project__:<root>` parent
 */
function collapseRoots(roots: TreeNode[], worktreeRoot: string): TreeNode | null {
  if (roots.length === 0) return null;
  if (roots.length === 1) return roots[0];
  const totals = roots.reduce(
    (acc, c) => ({
      input: acc.input + c.subtree_tokens.input,
      output: acc.output + c.subtree_tokens.output,
      cache_read: acc.cache_read + c.subtree_tokens.cache_read,
      cache_write: acc.cache_write + c.subtree_tokens.cache_write,
      descendant_count: acc.descendant_count + c.subtree_tokens.descendant_count + 1,
    }),
    { input: 0, output: 0, cache_read: 0, cache_write: 0, descendant_count: 0 },
  );
  const oldestStart = roots
    .map((r) => r.session.started_at)
    .sort()
    .at(0) as string;
  const virtualSession: Session = {
    session_id: `__project__:${worktreeRoot}`,
    parent_session_id: null,
    worktree_root: worktreeRoot,
    project_label: roots[0].session.project_label,
    cwd: worktreeRoot,
    agent_type: "project",
    state: "running",
    last_event_at: oldestStart,
    last_event_name: null,
    last_tool_name: null,
    started_at: oldestStart,
    completed_at: null,
    primary_model: null,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
  };
  return { session: virtualSession, children: roots, subtree_tokens: totals };
}

export function useTree(worktreeRoot: string | undefined): {
  tree: TreeNode | null;
  loading: boolean;
  error: string | null;
} {
  const mock = useMock();
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { lastEvent } = useStream({ kind: "session_update" });

  const fetchTree = useCallback(async (root: string, signal: { cancelled: boolean }) => {
    try {
      const res = await withRetry(() =>
        apiGet<TreeNode | TreeNode[]>(`/api/tree?worktree=${encodeURIComponent(root)}`),
      );
      if (signal.cancelled) return;
      const collapsed = Array.isArray(res) ? collapseRoots(res, root) : res;
      setTree(collapsed);
      setLoading(false);
    } catch (e) {
      if (signal.cancelled) return;
      setError((e as Error).message);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!worktreeRoot) {
      setTree(null);
      setLoading(false);
      return;
    }
    const signal = { cancelled: false };
    setLoading(true);
    setError(null);
    if (mock) {
      setTree(mockTree(worktreeRoot));
      setLoading(false);
      return () => {
        signal.cancelled = true;
      };
    }
    fetchTree(worktreeRoot, signal);
    return () => {
      signal.cancelled = true;
    };
  }, [mock, worktreeRoot, fetchTree]);

  // Refetch the tree when a session in this worktree updates — debounced
  // so a burst of SSE events doesn't fan into a burst of GETs.
  const refetchTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (mock || !worktreeRoot) return;
    if (!lastEvent || lastEvent.kind !== "session_update") return;
    if (refetchTimerRef.current !== null) {
      window.clearTimeout(refetchTimerRef.current);
    }
    const signal = { cancelled: false };
    refetchTimerRef.current = window.setTimeout(() => {
      refetchTimerRef.current = null;
      fetchTree(worktreeRoot, signal);
    }, REFETCH_DEBOUNCE_MS);
    return () => {
      signal.cancelled = true;
      if (refetchTimerRef.current !== null) {
        window.clearTimeout(refetchTimerRef.current);
        refetchTimerRef.current = null;
      }
    };
  }, [mock, worktreeRoot, lastEvent, fetchTree]);

  return { tree, loading, error };
}
