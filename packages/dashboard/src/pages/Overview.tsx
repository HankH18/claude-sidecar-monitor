import { useMemo } from "react";
import { Link } from "react-router";
import type { Session } from "../api/types";
import ActivityLine from "../components/ActivityLine";
import AgentKindIcon from "../components/AgentKindIcon";
import ElapsedClock from "../components/ElapsedClock";
import EmptyState from "../components/EmptyState";
import ProjectTreeSection from "../components/ProjectTreeSection";
import PullToRefreshIndicator from "../components/PullToRefreshIndicator";
import SessionLabel from "../components/SessionLabel";
import { ProjectGroupSkeleton } from "../components/Skeleton";
import StatePill from "../components/StatePill";
import TokenBadge from "../components/TokenBadge";
import Window from "../components/Window";
import { usePullToRefresh } from "../hooks/usePullToRefresh";
import { useSessions } from "../hooks/useSessions";
import { formatRelative } from "../lib/time";

const LIVE_STATES = new Set<Session["state"]>(["running", "tool", "waiting_user", "hung", "idle"]);

function projectKey(s: Session): string {
  return s.worktree_root;
}

function projectLabel(s: Session): string {
  return s.project_label ?? s.worktree_root.split("/").pop() ?? s.worktree_root;
}

function staleLabelFor(s: Session): string | undefined {
  // The collector also computes "stale" via thresholds; we apply a client
  // heuristic so the UI reads correctly even before the server marks it.
  if (s.state !== "running" && s.state !== "tool") return undefined;
  const last = Date.parse(s.last_event_at);
  if (Number.isNaN(last)) return undefined;
  const age = Date.now() - last;
  return age >= 60_000 ? "stale" : undefined;
}

export default function Overview() {
  const { sessions, loading, refetch } = useSessions();
  const ptr = usePullToRefresh(refetch, { enabled: !loading });

  const grouped = useMemo(() => {
    const live = sessions.filter((s) => LIVE_STATES.has(s.state));
    const map = new Map<string, Session[]>();
    for (const s of live) {
      const k = projectKey(s);
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(s);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [sessions]);

  const recentDone = useMemo(() => {
    return sessions
      .filter((s) => s.state === "done")
      .sort((a, b) => (a.completed_at ?? "").localeCompare(b.completed_at ?? ""))
      .slice(-5)
      .reverse();
  }, [sessions]);

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div>
          <div className="h-6 w-40 rounded bg-line/60 animate-pulse" />
          <div className="h-3 w-32 mt-2 rounded bg-line/40 animate-pulse" />
        </div>
        <ProjectGroupSkeleton rows={2} />
        <ProjectGroupSkeleton rows={1} />
      </div>
    );
  }

  const liveCount = grouped.reduce((acc, [, list]) => acc + list.length, 0);

  return (
    <div className="space-y-6">
      <PullToRefreshIndicator pull={ptr.pull} armed={ptr.armed} refreshing={ptr.refreshing} />
      <header>
        <h1 className="text-2xl font-semibold text-ink leading-tight">Live agents</h1>
        <p className="text-xs text-ink-muted mt-1">
          {liveCount} active across {grouped.length} project
          {grouped.length === 1 ? "" : "s"}
        </p>
      </header>

      {grouped.length === 0 ? (
        <EmptyState
          illustration="agents"
          title="Nothing running"
          message="Start a Claude Code session and it'll appear here within a second or two."
          action={
            <div className="space-y-2 text-left max-w-xs">
              <p className="text-[11px] text-ink-muted">
                First-run? After installing csm, verify hooks fire:
              </p>
              <pre className="bg-code-bg text-code-text border border-line rounded text-[11px] px-2 py-1.5 font-mono whitespace-pre-wrap break-all">
                csm doctor --gate-test
              </pre>
              <p className="text-[11px] text-ink-muted">
                Or read the{" "}
                <a
                  href="https://github.com/HankH18/claude-sidecar-monitor#quickstart"
                  target="_blank"
                  rel="noreferrer"
                  className="text-teal hover:text-cta underline"
                >
                  quickstart
                </a>
                .
              </p>
            </div>
          }
        />
      ) : (
        <div className="space-y-5">
          {grouped.map(([key, list]) => (
            <ProjectTreeSection key={key} worktreeRoot={key} projectLabel={projectLabel(list[0])} />
          ))}
        </div>
      )}

      <section aria-label="recent completions">
        <Window icon="doc" title="Recent completions" bodyClassName="p-0">
          {recentDone.length === 0 ? (
            <p className="text-xs text-ink-muted px-4 py-4">Nothing wrapped up yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {recentDone.map((s) => (
                <SessionRow key={s.session_id} s={s} />
              ))}
            </ul>
          )}
        </Window>
      </section>
    </div>
  );
}

function SessionRow({ s }: { s: Session }) {
  const stale = staleLabelFor(s);
  const live = LIVE_STATES.has(s.state);
  return (
    <li>
      <Link
        to={`/sessions/${s.session_id}`}
        className="flex items-center gap-3 px-3 py-3 min-h-12 hover:bg-surface-2 active:bg-surface-2"
      >
        <StatePill state={stale ? "idle" : s.state} label={stale} className="shrink-0" />
        <AgentKindIcon
          kind={s.agent_kind ?? null}
          confidence={s.agent_kind_confidence ?? null}
          className="shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1 text-sm text-ink">
            <SessionLabel session={s} className="truncate font-medium" />
            {s.last_tool_name ? (
              <span className="text-ink-muted text-xs truncate shrink-0">· {s.last_tool_name}</span>
            ) : null}
          </div>
          <ActivityLine
            summary={s.activity_summary ?? null}
            updatedAt={s.activity_updated_at ?? null}
            className="mt-0.5"
          />
          <div className="text-[11px] text-ink-muted truncate mt-0.5">
            {s.primary_model ?? "model?"} ·{" "}
            {s.state === "done" && s.completed_at ? (
              <span title={new Date(s.completed_at).toLocaleString()}>
                {formatRelative(s.completed_at)}
              </span>
            ) : (
              <ElapsedClock since={s.started_at} live={live} />
            )}
          </div>
        </div>
        <TokenBadge
          input={s.input_tokens}
          output={s.output_tokens}
          cacheRead={s.cache_read_tokens}
          cacheWrite={s.cache_write_tokens}
          className="shrink-0"
        />
      </Link>
    </li>
  );
}
