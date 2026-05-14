import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { apiGet, withRetry } from "../api/client";
import type { TreeNode as ApiTreeNode } from "../api/types";
import ActivityLine from "../components/ActivityLine";
import AgentKindIcon from "../components/AgentKindIcon";
import Breadcrumbs from "../components/Breadcrumbs";
import StatePill from "../components/StatePill";
import Window from "../components/Window";
import { useSessions } from "../hooks/useSessions";

/**
 * V2.C3 — single virtual subagent view.
 *
 * The collector merges virtual subagent rows into `GET /api/tree` rather
 * than exposing a dedicated endpoint, so for v0 we walk the relevant tree
 * and pluck out the matching virtual node.
 *
 * TODO(backend): replace this tree-walking helper with a direct
 * `GET /api/subagents/:virtualId` once the collector grows one. The
 * walk is correct but wastes a full tree fetch for what should be a
 * single-row lookup.
 */
async function findVirtualNode(
  worktreeRoot: string,
  virtualId: string,
): Promise<ApiTreeNode | null> {
  const roots = await withRetry(() =>
    apiGet<ApiTreeNode[] | ApiTreeNode>(`/api/tree?worktree=${encodeURIComponent(worktreeRoot)}`),
  );
  const list = Array.isArray(roots) ? roots : [roots];

  const stack: ApiTreeNode[] = [...list];
  while (stack.length) {
    const n = stack.pop()!;
    if (n.is_virtual && n.virtual_id === virtualId) return n;
    for (const c of n.children) stack.push(c);
  }
  return null;
}

export default function SubagentDetail() {
  const { virtualId: encodedId } = useParams();
  const virtualId = encodedId ? decodeURIComponent(encodedId) : "";
  const [parentSessionId, _toolUseId] = virtualId.split(":");

  const { sessions } = useSessions();
  // The parent session's worktree_root tells us which tree to walk.
  const parent = sessions.find((s) => s.session_id === parentSessionId) ?? null;
  const worktreeRoot = parent?.worktree_root ?? null;

  const [node, setNode] = useState<ApiTreeNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!virtualId || !worktreeRoot) {
      // Wait for sessions to populate; if there is no parent at all, we
      // can't find the subagent.
      if (sessions.length > 0 && !worktreeRoot) {
        setLoading(false);
        setError("Parent session not found.");
      }
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    setError(null);
    findVirtualNode(worktreeRoot, virtualId)
      .then((n) => {
        if (cancelled) return;
        setNode(n);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [virtualId, worktreeRoot, sessions.length]);

  if (!virtualId) {
    return <p className="text-sm text-ink-muted">No subagent id.</p>;
  }

  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <div className="h-3 w-12 rounded bg-line/60 animate-pulse" />
        <div className="h-5 w-2/3 rounded bg-line/60 animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-line/40 animate-pulse" />
      </div>
    );
  }

  if (error || !node) {
    return (
      <div className="space-y-3">
        <Breadcrumbs items={[{ label: "Live", to: "/live" }, { label: "Subagent" }]} />
        <h1 className="text-2xl font-semibold text-ink leading-tight">Subagent</h1>
        <p className="text-sm text-ink-muted">{error ?? "Subagent not found."}</p>
        {parentSessionId ? (
          <Link
            to={`/sessions/${parentSessionId}`}
            className="inline-flex items-center min-h-11 px-3 rounded-md text-xs text-teal hover:text-cta border border-line bg-surface hover:bg-surface-2"
          >
            ← parent session
          </Link>
        ) : null}
      </div>
    );
  }

  const session = node.session;
  const projectLabel =
    parent?.project_label ??
    (worktreeRoot ? (worktreeRoot.split("/").pop() ?? worktreeRoot) : "project");
  const projectHref = worktreeRoot ? `/projects/${encodeURIComponent(worktreeRoot)}` : "/";

  return (
    <div className="space-y-4" data-testid="subagent-detail">
      <Breadcrumbs
        items={[
          { label: "Live", to: "/live" },
          { label: projectLabel, to: projectHref },
          { label: "subagent" },
        ]}
      />

      <Window
        icon="doc"
        title={session.title ?? session.nickname ?? "subagent"}
        actions={<StatePill state={session.state} />}
      >
        <div className="space-y-2">
          <h1 className="text-base font-semibold text-ink truncate inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="text-ink-subtle font-mono text-sm">
              🜲
            </span>
            <AgentKindIcon
              kind={session.agent_kind ?? null}
              confidence={session.agent_kind_confidence ?? null}
            />
            <span className="truncate">{session.title ?? session.nickname ?? "subagent"}</span>
          </h1>
          {node.description ? (
            <p className="text-[11px] text-ink-muted">{node.description}</p>
          ) : null}
          <ActivityLine
            summary={session.activity_summary ?? null}
            updatedAt={session.activity_updated_at ?? null}
          />
        </div>
      </Window>

      <Window icon="doc" title="Subagent metadata" aria-label="subagent metadata">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <MetaItem label="started" value={fmtTs(session.started_at)} />
          <MetaItem label="completed" value={fmtTs(session.completed_at)} />
          <MetaItem label="state" value={session.state} />
          <MetaItem label="kind" value={(session.agent_kind ?? "—") as string} />
        </div>
      </Window>

      {parentSessionId ? (
        <Link
          to={`/sessions/${parentSessionId}`}
          className="inline-flex items-center min-h-11 px-3 rounded-md text-xs text-teal hover:text-cta border border-line bg-surface hover:bg-surface-2"
        >
          ← parent session ({parentSessionId.slice(0, 8)})
        </Link>
      ) : null}
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="text-ink font-mono text-sm mt-0.5 truncate">{value}</div>
    </div>
  );
}

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
