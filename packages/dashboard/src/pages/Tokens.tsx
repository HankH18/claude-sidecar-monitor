import { useMemo } from "react";
import { Link } from "react-router";
import type { TokensResponse } from "../api/types";
import EmptyState from "../components/EmptyState";
import PullToRefreshIndicator from "../components/PullToRefreshIndicator";
import { formatTokens } from "../components/TokenBadge";
import { usePullToRefresh } from "../hooks/usePullToRefresh";
import { useTokens } from "../hooks/useTokens";

interface DayBucket {
  date: string;
  byModel: Record<string, number>;
  total: number;
}

function buildBuckets(daily: TokensResponse["dailyTotals"]): DayBucket[] {
  const map = new Map<string, DayBucket>();
  for (const row of daily) {
    if (!map.has(row.date)) {
      map.set(row.date, { date: row.date, byModel: {}, total: 0 });
    }
    const b = map.get(row.date)!;
    // Sum input + output for the bar height (cache excluded so the chart
    // reflects "active" usage; cache is shown elsewhere).
    const value = row.input + row.output;
    b.byModel[row.model] = (b.byModel[row.model] ?? 0) + value;
    b.total += value;
  }
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

const MODEL_COLORS: Record<string, string> = {
  "claude-opus-4-7": "#10b981", // emerald
  "claude-sonnet-4-5": "#3b82f6", // blue
  unknown: "#64748b", // slate
};

function colorFor(model: string): string {
  return MODEL_COLORS[model] ?? "#a78bfa";
}

function StackedBarChart({ daily }: { daily: TokensResponse["dailyTotals"] }) {
  const buckets = useMemo(() => buildBuckets(daily), [daily]);
  const models = useMemo(() => {
    const set = new Set<string>();
    for (const b of buckets) for (const m of Object.keys(b.byModel)) set.add(m);
    return [...set].sort();
  }, [buckets]);
  const max = Math.max(1, ...buckets.map((b) => b.total));

  // SVG dims chosen to fit a 380px viewport with 14 bars.
  const width = 320;
  const height = 140;
  const pad = { top: 8, right: 8, bottom: 18, left: 8 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const barGap = 2;
  const barW = (innerW - barGap * (buckets.length - 1)) / buckets.length;

  return (
    <figure aria-label="daily tokens stacked bar chart">
      <svg
        role="img"
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-md"
        preserveAspectRatio="xMidYMid meet"
      >
        <title>Daily tokens by model (last 14 days)</title>
        {buckets.map((b, i) => {
          let yCursor = pad.top + innerH;
          const x = pad.left + i * (barW + barGap);
          return (
            <g key={b.date}>
              {models.map((m) => {
                const v = b.byModel[m] ?? 0;
                if (v <= 0) return null;
                const h = (v / max) * innerH;
                yCursor -= h;
                return (
                  <rect
                    key={m}
                    x={x}
                    y={yCursor}
                    width={barW}
                    height={h}
                    fill={colorFor(m)}
                    opacity={0.9}
                  >
                    <title>{`${b.date} · ${m} · ${formatTokens(v)}`}</title>
                  </rect>
                );
              })}
              {i === 0 || i === buckets.length - 1 ? (
                <text
                  x={x}
                  y={height - 4}
                  fontSize="8"
                  fill="#71717a"
                  textAnchor={i === 0 ? "start" : "end"}
                >
                  {b.date.slice(5)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-3 text-[10px] text-zinc-500 mt-2">
        {models.map((m) => (
          <span key={m} className="inline-flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block w-2 h-2 rounded-sm"
              style={{ backgroundColor: colorFor(m) }}
            />
            {m}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

/**
 * Tiny sparkline + at-a-glance "today vs 14-day average" signal. The label
 * flips green when today is below average, amber when comparable (±15%),
 * red when above. No threshold logic — purely visual signal.
 */
function TodaySparkline({ daily }: { daily: TokensResponse["dailyTotals"] }) {
  const { totals, today, avg } = useMemo(() => {
    const byDate = new Map<string, number>();
    for (const row of daily) {
      const v = row.input + row.output;
      byDate.set(row.date, (byDate.get(row.date) ?? 0) + v);
    }
    const sorted = [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const totals = sorted.map(([, v]) => v);
    const today = totals.length ? totals[totals.length - 1] : 0;
    // Average over the prior days only (excludes today, since we're
    // comparing "is today below typical?" vs. a window that includes itself).
    const prior = totals.slice(0, -1);
    const avg = prior.length ? prior.reduce((s, v) => s + v, 0) / prior.length : 0;
    return { totals, today, avg };
  }, [daily]);

  if (totals.length < 2) return null;

  // Color: green if <=85% of avg, red if >=115%, amber otherwise.
  const ratio = avg > 0 ? today / avg : 1;
  const color = ratio <= 0.85 ? "#34d399" : ratio >= 1.15 ? "#f87171" : "#fbbf24";
  const label = ratio <= 0.85 ? "below avg" : ratio >= 1.15 ? "above avg" : "near avg";

  // Build a tiny SVG polyline.
  const w = 80;
  const h = 24;
  const max = Math.max(1, ...totals);
  const stepX = totals.length > 1 ? w / (totals.length - 1) : w;
  const points = totals
    .map((v, i) => `${(i * stepX).toFixed(2)},${(h - (v / max) * h).toFixed(2)}`)
    .join(" ");
  const lastX = (totals.length - 1) * stepX;
  const lastY = h - (today / max) * h;

  return (
    <div
      className="inline-flex items-center gap-2 align-middle"
      title={`today: ${formatTokens(today)} · 14d avg: ${formatTokens(Math.round(avg))}`}
    >
      <svg
        role="img"
        aria-label={`today vs 14-day average — ${label}`}
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="block"
      >
        <title>today vs 14-day average — {label}</title>
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity={0.85}
        />
        <circle cx={lastX} cy={lastY} r={2.2} fill={color} />
      </svg>
      <span className="text-[11px]" style={{ color }}>
        {label}
      </span>
    </div>
  );
}

export default function Tokens() {
  const { data, loading, refetch } = useTokens();
  const ptr = usePullToRefresh(refetch, { enabled: !loading });

  if (loading || !data) {
    return (
      <div className="space-y-5" aria-busy="true">
        <div className="space-y-2">
          <div className="h-5 w-24 rounded bg-zinc-800/60 animate-pulse" />
          <div className="h-3 w-56 rounded bg-zinc-800/40 animate-pulse" />
        </div>
        <div className="h-3 w-32 rounded bg-zinc-800/40 animate-pulse" />
        <div className="h-32 rounded-md bg-zinc-800/40 animate-pulse" />
        <div className="h-32 rounded-md bg-zinc-800/40 animate-pulse" />
      </div>
    );
  }

  const hasAny =
    data.topSessions.length > 0 ||
    data.topProjects.length > 0 ||
    data.totalsByModel.length > 0 ||
    data.dailyTotals.length > 0;

  return (
    <div className="space-y-6">
      <PullToRefreshIndicator pull={ptr.pull} armed={ptr.armed} refreshing={ptr.refreshing} />
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-lg font-semibold text-zinc-100">Tokens</h1>
          {data.dailyTotals.length > 0 ? <TodaySparkline daily={data.dailyTotals} /> : null}
        </div>
        <p className="text-[11px] text-zinc-500">
          Absolute counts; reflects API-reported usage, not billing.
        </p>
      </header>

      {!hasAny ? (
        <EmptyState
          illustration="tokens"
          title="No token usage yet"
          message="Once an agent makes its first API call, totals roll up here. Token data first appears after a session has had at least one assistant turn."
        />
      ) : null}

      {data.topSessions.length > 0 ? (
        <section aria-label="top sessions last 24h" className="space-y-2">
          <h2 className="text-xs uppercase tracking-wide text-zinc-500">Top sessions (last 24h)</h2>
          <ul className="divide-y divide-zinc-800 rounded-md border border-zinc-800 overflow-hidden">
            {data.topSessions.map((s) => (
              <li key={s.session_id}>
                <Link
                  to={`/sessions/${s.session_id}`}
                  className="flex items-center justify-between gap-3 px-3 py-3 min-h-12 hover:bg-zinc-900/60"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-100 truncate">
                      {s.agent_type ?? "session"} · {s.project_label ?? s.worktree_root}
                    </div>
                    <div className="text-[11px] text-zinc-500 truncate mt-0.5">
                      {s.primary_model ?? "—"}
                    </div>
                  </div>
                  <div className="text-right font-mono tabular-nums text-xs text-zinc-100 shrink-0">
                    {formatTokens(s.input + s.output)}
                    <div className="text-[10px] text-zinc-500">cr {formatTokens(s.cache_read)}</div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.topProjects.length > 0 ? (
        <section aria-label="top projects all time" className="space-y-2">
          <h2 className="text-xs uppercase tracking-wide text-zinc-500">Top projects (all time)</h2>
          <ul className="divide-y divide-zinc-800 rounded-md border border-zinc-800 overflow-hidden">
            {data.topProjects.map((p) => (
              <li key={p.worktree_root}>
                <Link
                  to={`/projects/${encodeURIComponent(p.worktree_root)}`}
                  className="flex items-center justify-between gap-3 px-3 py-3 min-h-12 hover:bg-zinc-900/60"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-100 truncate">
                      {p.project_label ?? p.worktree_root}
                    </div>
                    <div className="text-[11px] text-zinc-500 truncate mt-0.5">
                      {(p as { session_count?: number }).session_count ?? 0} session
                      {(p as { session_count?: number }).session_count === 1 ? "" : "s"}
                    </div>
                  </div>
                  <div className="text-right font-mono tabular-nums text-xs text-zinc-100 shrink-0">
                    {formatTokens(p.input + p.output)}
                    <div className="text-[10px] text-zinc-500">cr {formatTokens(p.cache_read)}</div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.totalsByModel.length > 0 ? (
        <section aria-label="totals by model" className="space-y-2">
          <h2 className="text-xs uppercase tracking-wide text-zinc-500">By model</h2>
          <div className="rounded-md border border-zinc-800 overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-zinc-500">
                <tr>
                  <th className="text-left px-3 py-2">model</th>
                  <th className="text-right px-3 py-2">input</th>
                  <th className="text-right px-3 py-2">output</th>
                  <th className="text-right px-3 py-2 text-zinc-600">cr</th>
                  <th className="text-right px-3 py-2 text-zinc-600">cw</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {data.totalsByModel.map((m) => (
                  <tr key={m.model} className="border-t border-zinc-800">
                    <td className="px-3 py-2 text-zinc-100">{m.model}</td>
                    <td className="px-3 py-2 text-right">{formatTokens(m.input)}</td>
                    <td className="px-3 py-2 text-right">{formatTokens(m.output)}</td>
                    <td className="px-3 py-2 text-right text-zinc-500">
                      {formatTokens(m.cache_read)}
                    </td>
                    <td className="px-3 py-2 text-right text-zinc-500">
                      {formatTokens(m.cache_write)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section aria-label="daily totals chart" className="space-y-2">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500">Daily totals (14 days)</h2>
        {data.dailyTotals.length > 0 ? (
          <StackedBarChart daily={data.dailyTotals} />
        ) : (
          <p className="text-xs text-zinc-600 px-1">No daily totals available yet.</p>
        )}
      </section>

      <p className="text-[11px] text-zinc-500 leading-relaxed border-t border-zinc-800 pt-4">
        csm reports per-message API usage. For monthly billing limits, see your{" "}
        <a
          href="https://console.anthropic.com/"
          target="_blank"
          rel="noreferrer"
          className="text-zinc-400 hover:text-zinc-200 underline"
        >
          Anthropic account
        </a>
        .
      </p>
    </div>
  );
}
