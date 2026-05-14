import { type AgentKind, KIND_CONFIDENCE_MUTED } from "../api/types";

interface KindSpec {
  /** Single-glyph icon — unicode so we don't need an icon library. */
  glyph: string;
  /** Short label (used as accessible name + tooltip). */
  label: string;
  /** Tailwind text color for the high-confidence rendering. Warm palette. */
  tone: string;
}

/**
 * Each kind gets a distinct glyph and a unique-but-warm color so the
 * sidebar/tree reads as a glanceable palette rather than a kindergarten
 * rainbow. We lean on our `teal`, `info`, `cta`, `good`, `warn`, `bad`
 * tokens plus a couple of ink shades for breadth.
 */
const KIND_SPECS: Record<string, KindSpec> = {
  general: { glyph: "◇", label: "general", tone: "text-ink-muted" },
  explorer: { glyph: "⌕", label: "explorer", tone: "text-info" },
  reviewer: { glyph: "✓", label: "reviewer", tone: "text-good" },
  planner: { glyph: "≡", label: "planner", tone: "text-teal" },
  coder: { glyph: "❮❯", label: "coder", tone: "text-warn" },
  debugger: { glyph: "𝛌", label: "debugger", tone: "text-bad" },
  refactorer: { glyph: "⇋", label: "refactorer", tone: "text-teal" },
  tester: { glyph: "✓✓", label: "tester", tone: "text-good" },
};

const DEFAULT_SPEC: KindSpec = {
  glyph: "·",
  label: "agent",
  tone: "text-ink-muted",
};

export interface AgentKindIconProps {
  kind: AgentKind | string | null | undefined;
  confidence?: number | null;
  className?: string;
  /** Render label text alongside the glyph. */
  showLabel?: boolean;
}

/**
 * Tiny badge for an inferred agent_kind. Confidence below
 * `KIND_CONFIDENCE_MUTED` flips to muted styling so a low-quality guess
 * doesn't look authoritative.
 *
 * Inline glyph + tone — no icon library / no SVG fetch.
 */
export default function AgentKindIcon({
  kind,
  confidence,
  className = "",
  showLabel = false,
}: AgentKindIconProps) {
  if (!kind) return null;
  const spec = KIND_SPECS[kind] ?? DEFAULT_SPEC;
  const muted = typeof confidence === "number" && confidence < KIND_CONFIDENCE_MUTED;
  const tone = muted ? "text-ink-subtle opacity-60" : spec.tone;
  const ariaLabel = muted ? `${spec.label} (low confidence)` : spec.label;
  return (
    <span
      role="img"
      aria-label={ariaLabel}
      title={ariaLabel}
      data-kind={kind}
      data-muted={muted ? "true" : "false"}
      className={`inline-flex items-center gap-1 font-mono leading-none ${tone} ${className}`}
    >
      <span aria-hidden="true">{spec.glyph}</span>
      {showLabel ? <span className="text-[10px] uppercase tracking-wide">{spec.label}</span> : null}
    </span>
  );
}
