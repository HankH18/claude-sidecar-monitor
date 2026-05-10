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
 * Compact dual-line token display.
 *   line 1: input · output  (primary)
 *   line 2: cache_read · cache_write  (smaller, dimmer)
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
      className={`text-right leading-tight ${className}`}
      aria-label={`tokens: ${input} input, ${output} output, ${cacheRead} cache read, ${cacheWrite} cache write`}
    >
      <div className="text-xs text-zinc-200 font-mono">
        <span title="input tokens">{formatTokens(input)}</span>
        <span className="text-zinc-600 mx-1">·</span>
        <span title="output tokens">{formatTokens(output)}</span>
      </div>
      {showCache ? (
        <div className="text-[10px] text-zinc-500 font-mono">
          <span title="cache read">cr {formatTokens(cacheRead)}</span>
          {cacheWrite > 0 ? (
            <>
              <span className="text-zinc-700 mx-1">·</span>
              <span title="cache write">cw {formatTokens(cacheWrite)}</span>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
