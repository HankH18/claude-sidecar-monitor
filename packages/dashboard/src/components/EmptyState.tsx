import type { ReactNode } from "react";

/**
 * Friendly empty-state card. A small inline SVG illustration + headline + a
 * one-sentence next step. No external icon dependency — the SVGs use
 * `currentColor` so the parent class controls hue (we set a muted ink tone).
 *
 * Pass `illustration="agents" | "transcript" | "tokens"` to pick a relevant
 * vector; or pass your own ReactNode via `illustration={<svg…/>}`.
 */
export type EmptyIllustration = "agents" | "transcript" | "tokens" | "search";

interface EmptyStateProps {
  illustration?: EmptyIllustration | ReactNode;
  title: string;
  message: string;
  /** Optional CTA — e.g. a Link styled as a button. */
  action?: ReactNode;
  className?: string;
}

export default function EmptyState({
  illustration = "agents",
  title,
  message,
  action,
  className = "",
}: EmptyStateProps) {
  const art = isBuiltinKind(illustration) ? (
    <BuiltinIllustration kind={illustration} />
  ) : (
    illustration
  );
  return (
    <output
      className={`flex flex-col items-center justify-center text-center gap-3 py-10 px-6 rounded-md border border-dashed border-line bg-surface-2/60 ${className}`}
    >
      <span className="text-ink-subtle block" aria-hidden="true">
        {art}
      </span>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="text-xs text-ink-muted max-w-xs leading-relaxed">{message}</p>
      {action ? <span className="block mt-1">{action}</span> : null}
    </output>
  );
}

const BUILTIN_KINDS: ReadonlySet<EmptyIllustration> = new Set([
  "agents",
  "transcript",
  "tokens",
  "search",
]);

function isBuiltinKind(value: unknown): value is EmptyIllustration {
  return typeof value === "string" && BUILTIN_KINDS.has(value as EmptyIllustration);
}

function BuiltinIllustration({ kind }: { kind: EmptyIllustration }) {
  const common = { width: 64, height: 64, viewBox: "0 0 64 64", fill: "none" };
  switch (kind) {
    case "agents":
      // Concentric circles + a satellite — evokes "agents orbiting a project".
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <circle cx="32" cy="32" r="22" opacity="0.25" />
          <circle cx="32" cy="32" r="14" opacity="0.5" />
          <circle cx="32" cy="32" r="3" fill="currentColor" stroke="none" />
          <circle cx="32" cy="10" r="2.5" fill="currentColor" stroke="none" />
          <circle cx="54" cy="32" r="2.5" fill="currentColor" stroke="none" opacity="0.7" />
        </svg>
      );
    case "transcript":
      // Two stacked message bubbles.
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <rect x="8" y="14" width="36" height="18" rx="4" opacity="0.6" />
          <rect x="20" y="36" width="36" height="14" rx="4" opacity="0.4" />
        </svg>
      );
    case "tokens":
      // Three ascending bars.
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <rect x="12" y="38" width="10" height="14" rx="2" opacity="0.4" />
          <rect x="27" y="28" width="10" height="24" rx="2" opacity="0.6" />
          <rect x="42" y="18" width="10" height="34" rx="2" opacity="0.85" />
        </svg>
      );
    case "search":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <circle cx="28" cy="28" r="14" opacity="0.6" />
          <line x1="38" y1="38" x2="52" y2="52" />
        </svg>
      );
  }
}
