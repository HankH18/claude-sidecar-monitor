import { useMemo } from "react";
import { Tree } from "react-arborist";
import { Link, useNavigate, useParams } from "react-router";
import type { TreeNode as ApiTreeNode, Session } from "../api/types";
import EmptyState from "../components/EmptyState";
import { ProjectSummarySkeleton, TreeSkeleton } from "../components/Skeleton";
import { formatTokens } from "../components/TokenBadge";
import TreeRow, { toRowData, type TreeRowData } from "../components/TreeNode";
import { useSessions } from "../hooks/useSessions";
import { useTree } from "../hooks/useTree";

function flattenSessions(node: ApiTreeNode): Session[] {
  return [node.session, ...node.children.flatMap(flattenSessions)];
}

/** Compact in-page back affordance with ≥44pt tap target. */
function BackLink() {
  return (
    <Link
      to="/"
      className="inline-flex items-center gap-1 min-h-11 -mx-1 px-1 text-xs text-emerald-300 hover:text-emerald-200"
    >
      <span aria-hidden="true">←</span> back
    </Link>
  );
}

export default function ProjectDetail() {
  const { encoded } = useParams();
  const navigate = useNavigate();
  const worktreeRoot = encoded ? decodeURIComponent(encoded) : undefined;
  const { tree, loading } = useTree(worktreeRoot);
  const { sessions } = useSessions();

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
        <div className="h-3 w-12 rounded bg-zinc-800/60 animate-pulse" />
        <div className="h-6 w-2/3 rounded bg-zinc-800/60 animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-zinc-800/40 animate-pulse" />
        <ProjectSummarySkeleton />
        <TreeSkeleton rows={5} />
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="space-y-3">
        <BackLink />
        <h1 className="text-lg font-semibold text-zinc-100">Project</h1>
        <p className="text-sm text-zinc-500">Project not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <BackLink />
        <h1 className="text-lg font-semibold text-zinc-100">{projectLabel}</h1>
        <p className="text-[11px] text-zinc-500 break-all">{worktreeRoot}</p>
      </header>

      <section
        aria-label="project summary"
        className="grid grid-cols-2 gap-3 text-sm rounded-md border border-zinc-800 p-4"
      >
        <SummaryItem label="agents" value={String(summary.agents)} />
        <SummaryItem label="tool calls" value={String(summary.toolCalls)} />
        <SummaryItem
          label="oldest start"
          value={summary.oldest ? new Date(summary.oldest).toLocaleTimeString() : "—"}
        />
        <SummaryItem label="total tokens" value={formatTokens(summary.totalTokens)} />
      </section>

      <section aria-label="agent tree" className="rounded-md border border-zinc-800">
        {rows.length === 0 ? (
          <EmptyState
            illustration="agents"
            title="No sessions in this project"
            message="Sessions for this worktree will show up the moment a Claude Code agent starts work here."
            className="border-0 bg-transparent"
          />
        ) : (
          <Tree<TreeRowData>
            data={rows}
            openByDefault
            rowHeight={44}
            indent={16}
            width="100%"
            height={Math.min(440, 44 * countNodes(rows) + 8)}
            disableDrag
            disableDrop
            disableEdit
            onActivate={(node) => {
              const id = node.data.id;
              if (id.startsWith("__project__") || id.startsWith("__empty__")) return;
              navigate(`/sessions/${id}`);
            }}
          >
            {TreeRow}
          </Tree>
        )}
      </section>
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
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="text-zinc-100 font-mono text-sm mt-0.5">{value}</div>
    </div>
  );
}
