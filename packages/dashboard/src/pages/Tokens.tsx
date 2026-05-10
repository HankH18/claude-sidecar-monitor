import { useMemo } from "react";
import { Link } from "react-router";
import type { TokensResponse } from "../api/types";
import { formatTokens } from "../components/TokenBadge";
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

export default function Tokens() {
  const { data, loading } = useTokens();

  if (loading || !data) {
    return <div className="h-32 rounded-md bg-zinc-900/60 animate-pulse" aria-busy="true" />;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-zinc-100">Tokens</h1>
        <p className="text-[11px] text-zinc-600">
          Absolute counts; reflects API-reported usage, not billing.
        </p>
      </header>

      <section aria-label="top sessions last 24h">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
          Top sessions (last 24h)
        </h2>
        <ul className="divide-y divide-zinc-900 rounded-md border border-zinc-900">
          {data.topSessions.map((s) => (
            <li key={s.session_id}>
              <Link
                to={`/sessions/${s.session_id}`}
                className="flex items-center justify-between px-3 py-2 hover:bg-zinc-900/60"
              >
                <div className="min-w-0">
                  <div className="text-sm text-zinc-200 truncate">
                    {s.agent_type ?? "session"} · {s.project_label ?? s.worktree_root}
                  </div>
                  <div className="text-[10px] text-zinc-500 truncate">{s.primary_model ?? "—"}</div>
                </div>
                <div className="text-right font-mono text-xs text-zinc-200 shrink-0 ml-2">
                  {formatTokens(s.input + s.output)}
                  <div className="text-[9px] text-zinc-600">cr {formatTokens(s.cache_read)}</div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="top projects all time">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
          Top projects (all time)
        </h2>
        <ul className="divide-y divide-zinc-900 rounded-md border border-zinc-900">
          {data.topProjects.map((p) => (
            <li key={p.worktree_root}>
              <Link
                to={`/projects/${encodeURIComponent(p.worktree_root)}`}
                className="flex items-center justify-between px-3 py-2 hover:bg-zinc-900/60"
              >
                <div className="min-w-0">
                  <div className="text-sm text-zinc-200 truncate">
                    {p.project_label ?? p.worktree_root}
                  </div>
                  <div className="text-[10px] text-zinc-500 truncate">
                    {(p as { session_count?: number }).session_count ?? 0} session
                    {(p as { session_count?: number }).session_count === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="text-right font-mono text-xs text-zinc-200 shrink-0 ml-2">
                  {formatTokens(p.input + p.output)}
                  <div className="text-[9px] text-zinc-600">cr {formatTokens(p.cache_read)}</div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="totals by model">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">By model</h2>
        <div className="rounded-md border border-zinc-900 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="text-left px-2 py-1">model</th>
                <th className="text-right px-2 py-1">input</th>
                <th className="text-right px-2 py-1">output</th>
                <th className="text-right px-2 py-1 text-zinc-600">cr</th>
                <th className="text-right px-2 py-1 text-zinc-600">cw</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {data.totalsByModel.map((m) => (
                <tr key={m.model} className="border-t border-zinc-900">
                  <td className="px-2 py-1 text-zinc-200">{m.model}</td>
                  <td className="px-2 py-1 text-right">{formatTokens(m.input)}</td>
                  <td className="px-2 py-1 text-right">{formatTokens(m.output)}</td>
                  <td className="px-2 py-1 text-right text-zinc-500">
                    {formatTokens(m.cache_read)}
                  </td>
                  <td className="px-2 py-1 text-right text-zinc-500">
                    {formatTokens(m.cache_write)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="daily totals chart">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
          Daily totals (14 days)
        </h2>
        <StackedBarChart daily={data.dailyTotals} />
      </section>
    </div>
  );
}
