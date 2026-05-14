import type { SessionState } from "../api/types";

interface PillSpec {
  label: string;
  icon: string;
  /** Tailwind text + bg classes from our warm-state palette. */
  classes: string;
  /** When true, animate the icon dot + add a pulsing ring around the pill. */
  pulse?: boolean;
}

/**
 * Warm-state palette uses our `good` / `warn` / `bad` / `info` tokens with
 * a soft tinted background. We rely on the existing `/15` opacity helper
 * Tailwind generates for arbitrary opacities of theme colors, which gives
 * the soft-tinted card behind warm-toned text.
 */
const PILLS: Record<SessionState, PillSpec> = {
  running: {
    label: "running",
    icon: "●",
    classes: "bg-good/15 text-good ring-1 ring-good/30",
  },
  tool: {
    label: "running",
    icon: "●",
    classes: "bg-good/15 text-good ring-1 ring-good/30",
  },
  idle: {
    label: "stale",
    icon: "⏱",
    classes: "bg-warn/15 text-warn ring-1 ring-warn/30",
  },
  hung: {
    label: "hung",
    icon: "⚠",
    classes: "bg-bad/20 text-bad ring-1 ring-bad/50",
    pulse: true,
  },
  waiting_user: {
    label: "waiting",
    icon: "🔔",
    classes: "bg-info/15 text-info ring-1 ring-info/30",
  },
  done: {
    label: "done",
    icon: "✓",
    classes: "bg-ink-subtle/20 text-ink-muted ring-1 ring-line",
  },
};

export interface StatePillProps {
  state: SessionState;
  /** Optional override label (e.g. show "stale" for >60s without event). */
  label?: string;
  className?: string;
}

/**
 * Compact status badge.
 *
 * The pill carries three signals so it remains legible regardless of channel:
 *   1. background tint (color)         — quick scan
 *   2. icon glyph                       — colorblind / monochrome fallback
 *   3. text label                       — screen readers + clarity
 *
 * Hung sessions get an extra pulsing ring (`animate-pulse-ring`, defined in
 * `theme.css`) — a stronger signal than `animate-pulse`'s opacity dip.
 */
export default function StatePill({ state, label, className = "" }: StatePillProps) {
  const spec = PILLS[state] ?? PILLS.done;
  const text = label ?? spec.label;
  return (
    <output
      aria-label={`session state: ${text}`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${spec.classes} ${spec.pulse ? "animate-pulse animate-pulse-ring" : ""} ${className}`}
    >
      <span aria-hidden="true">{spec.icon}</span>
      <span>{text}</span>
    </output>
  );
}
