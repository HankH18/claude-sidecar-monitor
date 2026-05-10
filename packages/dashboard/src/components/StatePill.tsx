import type { SessionState } from "../api/types";

interface PillSpec {
  label: string;
  icon: string;
  text: string;
  bg: string;
  ring: string;
  /** When true, animate the icon dot + add a pulsing red ring around the pill. */
  pulse?: boolean;
}

const PILLS: Record<SessionState, PillSpec> = {
  running: {
    label: "running",
    icon: "●",
    text: "text-emerald-300",
    bg: "bg-emerald-500/15",
    ring: "ring-1 ring-emerald-500/40",
  },
  tool: {
    label: "running",
    icon: "●",
    text: "text-emerald-300",
    bg: "bg-emerald-500/15",
    ring: "ring-1 ring-emerald-500/40",
  },
  idle: {
    label: "stale",
    icon: "⏱",
    text: "text-yellow-300",
    bg: "bg-yellow-500/15",
    ring: "ring-1 ring-yellow-500/40",
  },
  hung: {
    label: "hung",
    icon: "⚠",
    text: "text-red-300",
    bg: "bg-red-500/20",
    ring: "ring-1 ring-red-500/60",
    pulse: true,
  },
  waiting_user: {
    label: "waiting",
    icon: "🔔",
    text: "text-orange-300",
    bg: "bg-orange-500/15",
    ring: "ring-1 ring-orange-500/40",
  },
  done: {
    label: "done",
    icon: "✓",
    text: "text-zinc-300",
    bg: "bg-zinc-700/40",
    ring: "ring-1 ring-zinc-600/40",
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
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${spec.bg} ${spec.text} ${spec.ring} ${spec.pulse ? "animate-pulse animate-pulse-ring" : ""} ${className}`}
    >
      <span aria-hidden="true">{spec.icon}</span>
      <span>{text}</span>
    </output>
  );
}
