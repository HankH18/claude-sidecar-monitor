import { useMemo } from "react";
import { Link } from "react-router";
import type { Session } from "../api/types";
import ElapsedClock from "../components/ElapsedClock";
import StatePill from "../components/StatePill";
import TokenBadge from "../components/TokenBadge";
import { useSessions } from "../hooks/useSessions";

const LIVE_STATES = new Set<Session["state"]>(["running", "tool", "waiting_user", "hung", "idle"]);

function projectKey(s: Session): string {
  return s.worktree_root;
}

function projectLabel(s: Session): string {
  return s.project_label ?? s.worktree_root.split("/").pop() ?? s.worktree_root;
}

function encodeWorktree(root: string): string {
  return encodeURIComponent(root);
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
  const { sessions, loading } = useSessions();

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
    return <SkeletonList />;
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-lg font-semibold text-zinc-100">Live agents</h1>
        <p className="text-xs text-zinc-500 mt-1">
          {grouped.reduce((acc, [, list]) => acc + list.length, 0)} active across {grouped.length}{" "}
          project{grouped.length === 1 ? "" : "s"}
        </p>
      </header>

      {grouped.length === 0 ? (
        <div className="text-sm text-zinc-500 py-8 text-center border border-dashed border-zinc-800 rounded-md">
          No active sessions.
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(([key, list]) => {
            const label = projectLabel(list[0]);
            return (
              <section key={key} className="space-y-1">
                <Link
                  to={`/projects/${encodeWorktree(key)}`}
                  className="flex items-center justify-between text-sm text-zinc-300 hover:text-zinc-100"
                >
                  <span className="font-medium truncate">{label}</span>
                  <span className="text-zinc-500 text-xs">
                    {list.length} agent{list.length === 1 ? "" : "s"} →
                  </span>
                </Link>
                <ul className="divide-y divide-zinc-900 rounded-md border border-zinc-900">
                  {list.map((s) => (
                    <SessionRow key={s.session_id} s={s} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      <section aria-label="recent completions">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Recent completions</h2>
        {recentDone.length === 0 ? (
          <p className="text-xs text-zinc-600">Nothing finished yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-900 rounded-md border border-zinc-900">
            {recentDone.map((s) => (
              <SessionRow key={s.session_id} s={s} />
            ))}
          </ul>
        )}
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
        className="flex items-center gap-2 px-3 py-2 hover:bg-zinc-900/60"
      >
        <StatePill state={stale ? "idle" : s.state} label={stale} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1 text-sm text-zinc-200 truncate">
            <span className="truncate">{s.agent_type ?? "session"}</span>
            {s.last_tool_name ? (
              <span className="text-zinc-500 text-xs truncate">· {s.last_tool_name}</span>
            ) : null}
          </div>
          <div className="text-[11px] text-zinc-500 truncate">
            {s.primary_model ?? "model?"} · <ElapsedClock since={s.started_at} live={live} />
          </div>
        </div>
        <TokenBadge
          input={s.input_tokens}
          output={s.output_tokens}
          cacheRead={s.cache_read_tokens}
          cacheWrite={s.cache_write_tokens}
        />
      </Link>
    </li>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-14 rounded-md bg-zinc-900/60 animate-pulse" />
      ))}
    </div>
  );
}
