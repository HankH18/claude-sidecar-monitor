import { formatDuration, formatLocalShort, formatRelative } from "../lib/time";
import { formatTokens } from "./TokenBadge";

export interface SessionStatsLineProps {
  startedAt: string;
  /** Most recent activity — used for the "last active" cell. */
  lastEventAt?: string | null;
  /** When set, duration is computed up to this instant (otherwise: now). */
  completedAt?: string | null;
  /** True while the session is still live — drives the duration's accent. */
  live?: boolean;
  /** input + output total. Pass `null` to suppress the "total" cell. */
  totalTokens?: number | null;
  /** Trailing-60-min token spend. `null` → render an em-dash. */
  tokensLastHour?: number | null;
  /** When true, drop the token columns entirely (for virtual subagent rows). */
  hideTokens?: boolean;
  className?: string;
}

/**
 * V3 — compact per-row stats line. Sits beneath the activity digest on tree
 * rows + the metadata block on SessionDetail.
 *
 * Layout target: a single 11-12px tabular line. On a 380px phone we render:
 *   started · duration · total · /h
 * dropping "last active" if it would overflow (started + relative-last are
 * redundant when both are recent). Tabular numerals keep the columns from
 * dancing on every render.
 *
 * For virtual subagent rows we render the same row shape but with the
 * token columns suppressed (we can't attribute per-subagent yet — v2.1).
 */
export default function SessionStatsLine({
  startedAt,
  lastEventAt,
  completedAt,
  live = false,
  totalTokens,
  tokensLastHour,
  hideTokens = false,
  className = "",
}: SessionStatsLineProps) {
  const startedT = Date.parse(startedAt);
  const startedShort = Number.isNaN(startedT) ? "—" : formatLocalShort(startedT);
  const startedIsoTitle = Number.isNaN(startedT) ? undefined : new Date(startedT).toISOString();

  const lastT = lastEventAt ? Date.parse(lastEventAt) : Number.NaN;
  const lastRelative = Number.isFinite(lastT) ? formatRelative(lastT) : "";
  const lastTooltip = Number.isFinite(lastT) ? new Date(lastT).toLocaleString() : undefined;

  // Duration: started_at → (completed_at ?? now).
  const endT = completedAt ? Date.parse(completedAt) : Date.now();
  const durSeconds = Number.isFinite(startedT) ? Math.max(0, (endT - startedT) / 1000) : 0;
  const duration = formatDuration(durSeconds);

  const totalShown = !hideTokens && totalTokens !== null && totalTokens !== undefined;
  const lastHourShown = !hideTokens;

  return (
    <div
      data-testid="session-stats-line"
      className={`flex items-center gap-2 text-[11px] text-ink-subtle tabular-nums leading-tight ${className}`}
    >
      <span title={startedIsoTitle} className="shrink-0">
        <span className="text-ink-subtle/80">start</span>{" "}
        <span className="text-ink-muted">{startedShort}</span>
      </span>

      {lastRelative ? (
        <span title={lastTooltip} className="shrink-0 hidden sm:inline">
          <span className="text-ink-subtle/80">·</span>{" "}
          <span className="text-ink-muted">{lastRelative}</span>
        </span>
      ) : null}

      <span className="shrink-0">
        <span className="text-ink-subtle/80">·</span>{" "}
        <span className={live ? "text-teal" : "text-ink-muted"}>{duration}</span>
        {live ? (
          <span aria-hidden="true" className="ml-0.5 text-teal/70">
            ●
          </span>
        ) : null}
      </span>

      {totalShown ? (
        <span className="shrink-0" title="total tokens (input + output)">
          <span className="text-ink-subtle/80">·</span>{" "}
          <span className="text-ink-muted font-mono">{formatTokens(totalTokens ?? 0)}</span>
        </span>
      ) : null}

      {lastHourShown ? (
        <span
          className="shrink-0 ml-auto"
          title="tokens in the trailing 60 minutes (input + output)"
        >
          <span
            className={`font-mono ${
              tokensLastHour != null && tokensLastHour > 0 ? "text-teal" : "text-ink-subtle"
            }`}
          >
            {tokensLastHour == null ? "—" : `${formatTokens(tokensLastHour)}/h`}
          </span>
        </span>
      ) : null}
    </div>
  );
}
