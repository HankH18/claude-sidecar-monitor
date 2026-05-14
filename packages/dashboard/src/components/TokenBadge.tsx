interface TokenBadgeProps {
  input: number;
  output: number;
  cacheRead?: number;
  cacheWrite?: number;
  className?: string;
}

export function formatTokens(n: number): string {
  if (n < 1_000) return `${n}`;
  if (n < 1_000_000) {
    const v = n / 1_000;
    return v >= 10 ? `${v.toFixed(0)}K` : `${v.toFixed(1)}K`;
  }
  const v = n / 1_000_000;
  return v >= 10 ? `${v.toFixed(0)}M` : `${v.toFixed(2)}M`;
}

/**
 * Compact token display with three explicit levels of typographic emphasis:
 *
 *   1. PRIMARY — input tokens (the cost driver) at text-sm, ink color.
 *   2. SECONDARY — output tokens at text-xs, muted ink.
 *   3. TERTIARY — cache read/write at text-[10px], subtle ink.
 *
 * The eye should land on the state pill first, agent_type second, and only
 * then absorb the token magnitude — keeping `text-sm` here (not text-base)
 * preserves that order on Live rows.
 */
export default function TokenBadge({
  input,
  output,
  cacheRead = 0,
  cacheWrite = 0,
  className = "",
}: TokenBadgeProps) {
  const showCache = cacheRead > 0 || cacheWrite > 0;
  return (
    <div
      className={`text-right leading-tight font-mono tabular-nums ${className}`}
      aria-label={`tokens: ${input} input, ${output} output, ${cacheRead} cache read, ${cacheWrite} cache write`}
    >
      <div>
        <span className="text-sm text-ink" title="input tokens">
          {formatTokens(input)}
        </span>
        <span className="text-ink-subtle mx-1" aria-hidden="true">
          ·
        </span>
        <span className="text-xs text-ink-muted" title="output tokens">
          {formatTokens(output)}
        </span>
      </div>
      {showCache ? (
        <div className="text-[10px] text-ink-subtle">
          <span title="cache read">cr {formatTokens(cacheRead)}</span>
          {cacheWrite > 0 ? (
            <>
              <span className="text-ink-subtle mx-1" aria-hidden="true">
                ·
              </span>
              <span title="cache write">cw {formatTokens(cacheWrite)}</span>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
