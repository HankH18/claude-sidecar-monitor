import { useMemo } from "react";
import { Link } from "react-router";
import type { DashboardKpis } from "../api/types";
import EmptyState from "../components/EmptyState";
import { formatTokens } from "../components/TokenBadge";
import Window from "../components/Window";
import { useDashboard } from "../hooks/useDashboard";

/**
 * V3 KPI landing — "the central dashboard" per user feedback.
 *
 * Big numbers up top (live agents, hung, tokens today, tokens this hour),
 * a 60-bucket events-per-minute sparkline below them, and a couple of
 * top-N tables. The actual list of agents lives one click away at /live.
 */

function StatTile({
  label,
  value,
  sublabel,
  href,
  tone = "default",
}: {
  label: string;
  value: string;
  sublabel?: string;
  href?: string;
  tone?: "default" | "alert" | "active";
}) {
  const toneClass = tone === "alert" ? "text-bad" : tone === "active" ? "text-teal" : "text-ink";
  const body = (
    <div className="flex flex-col items-start gap-1 p-4 min-h-24">
      <div className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className={`text-3xl font-semibold tabular-nums leading-none ${toneClass}`}>{value}</div>
      {sublabel ? <div className="text-[11px] text-ink-subtle mt-auto">{sublabel}</div> : null}
    </div>
  );
  if (href) {
    return (
      <Link
        to={href}
        className="rounded-md border border-line bg-surface hover:bg-surface-2 shadow-sm transition-colors block"
      >
        {body}
      </Link>
    );
  }
  return <div className="rounded-md border border-line bg-surface shadow-sm">{body}</div>;
}

/**
 * 60-bar sparkline of events-per-minute. Each bar is ~4px wide with a
 * 1px gap; total ~300px wide which fits the 380px viewport with margins.
 * Heights normalised to the busiest minute in the window so the strip
 * always reads as "shape of recent activity" regardless of absolute rate.
 */
function Sparkline({ buckets }: { buckets: DashboardKpis["events_per_minute_60m"] }) {
  const max = useMemo(() => {
    let m = 0;
    for (const b of buckets) if (b.count > m) m = b.count;
    return m;
  }, [buckets]);

  if (buckets.length === 0) {
    return <p className="text-xs text-ink-subtle px-3 py-2">No events recorded yet.</p>;
  }

  return (
    <div className="px-3 pb-3 pt-1">
      <div className="flex items-end gap-px h-16" aria-label="events per minute, last 60 minutes">
        {buckets.map((b) => {
          const h = max === 0 ? 0 : Math.max(2, Math.round((b.count / max) * 100));
          return (
            <div
              key={b.ts}
              title={`${b.ts}: ${b.count} event${b.count === 1 ? "" : "s"}`}
              className={`flex-1 rounded-sm ${b.count === 0 ? "bg-line/60" : "bg-teal/70"}`}
              style={{ height: `${h}%` }}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-[10px] text-ink-subtle mt-1">
        <span>60 min ago</span>
        <span>now</span>
      </div>
    </div>
  );
}

function StateBreakdown({ counts }: { counts: DashboardKpis["state_counts"] }) {
  const entries: Array<[string, number, string]> = [
    ["running", counts.running, "text-good"],
    ["tool", counts.tool, "text-good"],
    ["waiting", counts.waiting_user, "text-warn"],
    ["idle", counts.idle, "text-ink-muted"],
    ["hung", counts.hung, "text-bad"],
  ];
  return (
    <ul className="divide-y divide-line">
      {entries.map(([label, count, tone]) => (
        <li key={label} className="flex items-center justify-between px-3 py-2 text-sm">
          <span className="text-ink-muted">{label}</span>
          <span className={`tabular-nums font-medium ${count > 0 ? tone : "text-ink-subtle"}`}>
            {count}
          </span>
        </li>
      ))}
    </ul>
  );
}

function TopModels({ models }: { models: DashboardKpis["top_models_today"] }) {
  if (models.length === 0) {
    return <p className="text-xs text-ink-subtle px-3 py-3">No model usage in the last 24h.</p>;
  }
  // Width-normalise the bars by the busiest model.
  const max = Math.max(...models.map((m) => m.input + m.output));
  return (
    <ul className="divide-y divide-line">
      {models.map((m) => {
        const total = m.input + m.output;
        const pct = max === 0 ? 0 : Math.round((total / max) * 100);
        return (
          <li key={m.model} className="px-3 py-2 space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-ink truncate">{m.model}</span>
              <span className="tabular-nums text-ink-muted">{formatTokens(total)}</span>
            </div>
            <div className="h-1 rounded-full bg-line/60 overflow-hidden">
              <div className="h-full bg-teal/80" style={{ width: `${pct}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function Dashboard() {
  const { kpis, loading, error } = useDashboard();

  if (loading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-6 w-40 rounded bg-surface-2 animate-pulse" />
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-md bg-surface border border-line animate-pulse" />
          ))}
        </div>
        <div className="h-32 rounded-md bg-surface border border-line animate-pulse" />
      </div>
    );
  }

  if (error || kpis === null) {
    return (
      <EmptyState
        illustration="agents"
        title="Dashboard unavailable"
        message={
          error
            ? `Couldn't reach the collector: ${error}`
            : "No KPI data yet. Once an agent runs, this fills in."
        }
      />
    );
  }

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-display text-ink">Dashboard</h1>
        <p className="text-small text-ink-subtle">
          {kpis.live_sessions} live · {formatTokens(kpis.total_tokens_today)} today
          {kpis.hung_sessions > 0 ? (
            <>
              {" · "}
              <span className="text-bad">{kpis.hung_sessions} hung</span>
            </>
          ) : null}
        </p>
      </header>

      <section aria-label="top stats" className="grid grid-cols-2 gap-3">
        <StatTile
          label="Live agents"
          value={String(kpis.live_sessions)}
          sublabel="non-done sessions"
          href="/live"
          tone={kpis.live_sessions > 0 ? "active" : "default"}
        />
        <StatTile
          label="Hung"
          value={String(kpis.hung_sessions)}
          sublabel={kpis.hung_sessions > 0 ? "needs attention" : "all healthy"}
          href={kpis.hung_sessions > 0 ? "/live" : undefined}
          tone={kpis.hung_sessions > 0 ? "alert" : "default"}
        />
        <StatTile
          label="Tokens today"
          value={formatTokens(kpis.total_tokens_today)}
          sublabel="last 24h, in + out"
          href="/tokens"
        />
        <StatTile
          label="This hour"
          value={formatTokens(kpis.total_tokens_last_hour)}
          sublabel={`${kpis.events_last_hour} event${kpis.events_last_hour === 1 ? "" : "s"}`}
          tone={kpis.total_tokens_last_hour > 0 ? "active" : "default"}
        />
      </section>

      <Window title="Events / minute (last hour)" icon="agents" bodyClassName="p-0">
        <Sparkline buckets={kpis.events_per_minute_60m} />
      </Window>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Window title="Live by state" icon="agents" bodyClassName="p-0">
          <StateBreakdown counts={kpis.state_counts} />
        </Window>
        <Window title="Top models (24h)" icon="tokens" bodyClassName="p-0">
          <TopModels models={kpis.top_models_today} />
        </Window>
      </div>

      <nav aria-label="drill-down" className="flex flex-wrap gap-2 pt-1">
        <Link
          to="/live"
          className="inline-flex items-center min-h-11 px-4 rounded-md border border-line-strong bg-surface text-ink hover:bg-surface-2 text-sm font-medium"
        >
          Live agents →
        </Link>
        <Link
          to="/tokens"
          className="inline-flex items-center min-h-11 px-4 rounded-md border border-line-strong bg-surface text-ink hover:bg-surface-2 text-sm font-medium"
        >
          Token breakdown →
        </Link>
        <Link
          to="/settings"
          className="inline-flex items-center min-h-11 px-4 rounded-md border border-line-strong bg-surface text-ink hover:bg-surface-2 text-sm font-medium"
        >
          Settings →
        </Link>
      </nav>

      <p className="text-[10px] text-ink-subtle tabular-nums">
        as of {new Date(kpis.as_of).toLocaleTimeString()}
      </p>
    </div>
  );
}
