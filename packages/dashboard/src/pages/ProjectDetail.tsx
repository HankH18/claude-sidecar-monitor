import { useCallback, useMemo, useRef } from "react";
import { Tree, type TreeApi } from "react-arborist";
import { useNavigate, useParams } from "react-router";
import type { TreeNode as ApiTreeNode, Session } from "../api/types";
import Breadcrumbs from "../components/Breadcrumbs";
import EmptyState from "../components/EmptyState";
import { ProjectSummarySkeleton, TreeSkeleton } from "../components/Skeleton";
import { formatTokens } from "../components/TokenBadge";
import TreeRow, { TREE_ROW_HEIGHT, toRowData, type TreeRowData } from "../components/TreeNode";
import Window from "../components/Window";
import { useSessions } from "../hooks/useSessions";
import { useTree } from "../hooks/useTree";

function flattenSessions(node: ApiTreeNode): Session[] {
  return [node.session, ...node.children.flatMap(flattenSessions)];
}

const TREE_STATE_PREFIX = "csm.tree.openIds.";

/**
 * Persist react-arborist's open/closed decisions to localStorage keyed by
 * worktree_root. Round 1 the tree reset to fully-expanded on every refetch;
 * for a project with 20+ children this was disorienting since the user's
 * collapse decisions evaporated each time the SSE stream nudged a refetch.
 */
function loadOpenIds(worktreeRoot: string | undefined): Record<string, boolean> | undefined {
  if (!worktreeRoot || typeof localStorage === "undefined") return undefined;
  try {
    const raw = localStorage.getItem(`${TREE_STATE_PREFIX}${worktreeRoot}`);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") return parsed as Record<string, boolean>;
  } catch {
    // Corrupt entry — clobber on next save.
  }
  return undefined;
}

function saveOpenIds(worktreeRoot: string | undefined, ids: Record<string, boolean>): void {
  if (!worktreeRoot || typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(`${TREE_STATE_PREFIX}${worktreeRoot}`, JSON.stringify(ids));
  } catch {
    // Quota / disabled storage; nothing meaningful we can do.
  }
}

export default function ProjectDetail() {
  const { encoded } = useParams();
  const navigate = useNavigate();
  const worktreeRoot = encoded ? decodeURIComponent(encoded) : undefined;
  const { tree, loading } = useTree(worktreeRoot);
  const { sessions } = useSessions();
  const treeRef = useRef<TreeApi<TreeRowData> | null>(null);

  // Snapshot the persisted open-state once per worktree change so we can
  // hand it to react-arborist via `initialOpenState`. Mutations are saved
  // back through the onToggle callback.
  const initialOpenState = useMemo(() => loadOpenIds(worktreeRoot), [worktreeRoot]);

  const persistOpenState = useCallback(() => {
    if (!treeRef.current) return;
    // react-arborist exposes a Map-like via .openState — copy the unfiltered
    // map (the only one we use; filtered would require a search term) into
    // a plain serializable object.
    const map = treeRef.current.openState;
    const ids: Record<string, boolean> = {};
    for (const [id, open] of Object.entries(map)) ids[id] = !!open;
    saveOpenIds(worktreeRoot, ids);
  }, [worktreeRoot]);

  // The persisted state is handed to <Tree> via initialOpenState, which
  // honors it across data refetches. No manual re-apply needed.

  const rows = useMemo<TreeRowData[]>(() => {
    if (!tree) return [];
    // If our tree root is a synthetic "project" node, skip it and show its
    // children at the top level so the tree reads naturally.
    if (tree.session.session_id.startsWith("__project__")) {
      return tree.children.map(toRowData);
    }
    return [toRowData(tree)];
  }, [tree]);

  const summary = useMemo(() => {
    if (!tree) {
      return { agents: 0, oldest: null, totalTokens: 0, toolCalls: 0 };
    }
    const all = flattenSessions(tree).filter(
      (s) => !s.session_id.startsWith("__project__") && !s.session_id.startsWith("__empty__"),
    );
    const oldest = all.reduce<string | null>((acc, s) => {
      if (!acc) return s.started_at;
      return s.started_at < acc ? s.started_at : acc;
    }, null);
    const total =
      tree.subtree_tokens.input +
      tree.subtree_tokens.output +
      tree.subtree_tokens.cache_read +
      tree.subtree_tokens.cache_write;
    // Tool-call count isn't on Session — use the live `last_tool_name` presence
    // as a proxy or 0; collector will replace with real count post-handoff.
    const toolCalls = all.filter((s) => s.last_tool_name).length;
    return {
      agents: all.length,
      oldest,
      totalTokens: total,
      toolCalls,
    };
  }, [tree]);

  const projectLabel = useMemo(() => {
    if (!worktreeRoot) return "(unknown)";
    if (sessions.length) {
      const match = sessions.find((s) => s.worktree_root === worktreeRoot);
      if (match?.project_label) return match.project_label;
    }
    return worktreeRoot.split("/").pop() ?? worktreeRoot;
  }, [worktreeRoot, sessions]);

  if (loading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-3 w-12 rounded bg-line/60 animate-pulse" />
        <div className="h-6 w-2/3 rounded bg-line/60 animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-line/40 animate-pulse" />
        <ProjectSummarySkeleton />
        <TreeSkeleton rows={5} />
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="space-y-3">
        <Breadcrumbs items={[{ label: "Live", to: "/" }, { label: "Project" }]} />
        <h1 className="text-2xl font-semibold text-ink">Project</h1>
        <p className="text-sm text-ink-muted">Project not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Breadcrumbs items={[{ label: "Live", to: "/" }, { label: projectLabel }]} />
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink leading-tight">{projectLabel}</h1>
        <p className="text-[11px] text-ink-muted break-all">{worktreeRoot}</p>
      </header>

      <Window icon="doc" title="Summary" aria-label="project summary">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <SummaryItem label="agents" value={String(summary.agents)} />
          <SummaryItem label="tool calls" value={String(summary.toolCalls)} />
          <SummaryItem
            label="oldest start"
            value={summary.oldest ? new Date(summary.oldest).toLocaleTimeString() : "—"}
          />
          <SummaryItem label="total tokens" value={formatTokens(summary.totalTokens)} />
        </div>
      </Window>

      <Window icon="agents" title="Agent tree" aria-label="agent tree" bodyClassName="p-0">
        {rows.length === 0 ? (
          <EmptyState
            illustration="agents"
            title="No sessions in this project"
            message="Sessions for this worktree show up the moment a Claude Code agent starts work here."
            className="border-0 bg-transparent"
          />
        ) : (
          <Tree<TreeRowData>
            data={rows}
            ref={treeRef}
            openByDefault
            initialOpenState={initialOpenState}
            rowHeight={TREE_ROW_HEIGHT}
            indent={16}
            width="100%"
            height={Math.min(640, TREE_ROW_HEIGHT * countNodes(rows) + 8)}
            disableDrag
            disableDrop
            disableEdit
            onToggle={persistOpenState}
            onActivate={(node) => {
              const id = node.data.id;
              if (id.startsWith("__project__") || id.startsWith("__empty__")) return;
              // V2.C3 — virtual subagent rows route to /subagents/:virtualId.
              if (node.data.node.is_virtual) {
                navigate(`/subagents/${encodeURIComponent(id)}`);
                return;
              }
              navigate(`/sessions/${id}`);
            }}
          >
            {TreeRow}
          </Tree>
        )}
      </Window>
    </div>
  );
}

function countNodes(rows: TreeRowData[]): number {
  let n = 0;
  const walk = (rs: TreeRowData[]) => {
    for (const r of rs) {
      n++;
      if (r.children?.length) walk(r.children);
    }
  };
  walk(rows);
  return Math.max(n, 1);
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="text-ink font-mono text-sm mt-0.5">{value}</div>
    </div>
  );
}
