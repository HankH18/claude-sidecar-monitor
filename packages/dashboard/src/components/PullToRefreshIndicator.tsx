/**
 * Visual companion to `usePullToRefresh`.
 *
 * Renders a thin overlay strip at the top of the page that translates with
 * the pull distance. The label flips between "Pull to refresh", "Release to
 * refresh", and "Refreshing…" based on which leg of the gesture we're on.
 *
 * The indicator does not capture pointer events — the gesture lives on the
 * page below.
 */

interface Props {
  pull: number;
  armed: boolean;
  refreshing: boolean;
  className?: string;
}

export default function PullToRefreshIndicator({ pull, armed, refreshing, className = "" }: Props) {
  if (pull === 0 && !refreshing) return null;
  const label = refreshing ? "Refreshing…" : armed ? "Release to refresh" : "Pull to refresh";
  // Cap visible translate so it doesn't push too much UI down.
  const ty = Math.min(pull, 56);
  const opacity = Math.min(1, Math.max(0.4, pull / 56));
  return (
    <output
      aria-live="polite"
      className={`block text-center text-[11px] text-zinc-400 select-none pointer-events-none ${className}`}
      style={{
        transform: `translateY(${ty - 28}px)`,
        opacity,
        transition: refreshing ? "transform 0.2s ease-out" : undefined,
      }}
      data-testid="ptr-indicator"
    >
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className={`inline-block w-2 h-2 rounded-full bg-emerald-400 ${
            refreshing ? "animate-pulse" : ""
          }`}
        />
        {label}
      </span>
    </output>
  );
}
