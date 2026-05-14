import type { ReactNode } from "react";

/**
 * "OS window" container — small title bar, light surface, subtle border.
 *
 * Used selectively for major content cards (project tree, session metadata,
 * settings groups, empty-state callouts). NOT used for tiny rows — that
 * would crowd the layout. Target: 1–3 windows visible per page.
 *
 * Visual treatment:
 *   - 28-32px title bar in `bg-titlebar` with a tiny inline-SVG doc icon,
 *     the title text, and optional right-aligned actions
 *   - Border below the title bar separating it from the body
 *   - Body uses `bg-surface` with a default `p-4`; passing `bodyClassName`
 *     overrides (e.g. for tree containers that want zero padding)
 */

export type WindowIcon =
  | "doc" /* a tiny page corner */
  | "agents" /* concentric dots */
  | "transcript" /* speech bubble */
  | "tokens" /* mini bar chart */
  | "settings" /* gear (simple) */
  | "approval" /* clipboard tick */
  | "alert" /* triangle bang */
  | "none";

export interface WindowProps {
  title: ReactNode;
  icon?: WindowIcon;
  /** Right-aligned action slot in the title bar (icon buttons, status, etc.). */
  actions?: ReactNode;
  /** ClassName for the outer wrapper. */
  className?: string;
  /** Override the body wrapper class (e.g. `p-0` for tree containers). */
  bodyClassName?: string;
  /** Accessible label for the wrapping section. Defaults to the title text
   *  when it's a string. */
  "aria-label"?: string;
  children: ReactNode;
}

function IconGlyph({ kind }: { kind: WindowIcon }) {
  if (kind === "none") return null;
  // 14×14 inline SVG, currentColor — sits in the title bar muted ink color.
  const common = { width: 14, height: 14, viewBox: "0 0 14 14", fill: "none" };
  switch (kind) {
    case "agents":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <circle cx="7" cy="7" r="5" opacity="0.45" />
          <circle cx="7" cy="7" r="1.4" fill="currentColor" stroke="none" />
          <circle cx="7" cy="2" r="0.9" fill="currentColor" stroke="none" />
        </svg>
      );
    case "transcript":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <rect x="1.5" y="2.5" width="9" height="6" rx="1.2" opacity="0.7" />
          <rect x="4" y="6.5" width="9" height="5" rx="1.2" opacity="0.5" />
        </svg>
      );
    case "tokens":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <rect x="2" y="8" width="2" height="4" rx="0.4" />
          <rect x="6" y="5.5" width="2" height="6.5" rx="0.4" opacity="0.75" />
          <rect x="10" y="3" width="2" height="9" rx="0.4" opacity="0.55" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <circle cx="7" cy="7" r="2" />
          <path d="M7 1.5v1.6M7 10.9v1.6M1.5 7h1.6M10.9 7h1.6M3 3l1.1 1.1M9.9 9.9L11 11M3 11l1.1-1.1M9.9 4.1L11 3" />
        </svg>
      );
    case "approval":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <rect x="3" y="2" width="8" height="10" rx="1" opacity="0.6" />
          <path d="M5 7l1.3 1.4L9 5.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "alert":
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <path d="M7 2l5.2 9.5H1.8L7 2z" />
          <path d="M7 6v3" strokeLinecap="round" />
          <circle cx="7" cy="10.2" r="0.6" fill="currentColor" stroke="none" />
        </svg>
      );
    default:
      // "doc" — a page with a folded corner.
      return (
        <svg {...common} stroke="currentColor" strokeWidth={1.2} aria-hidden="true">
          <path d="M3 1.5h5.2L11 4.2V12a0.5 0.5 0 01-0.5 0.5h-7.5A0.5 0.5 0 012.5 12V2a0.5 0.5 0 01.5-.5z" />
          <path d="M8 1.5V4.2h3" strokeLinejoin="round" />
        </svg>
      );
  }
}

export default function Window({
  title,
  icon = "doc",
  actions,
  className = "",
  bodyClassName = "p-4",
  "aria-label": ariaLabel,
  children,
}: WindowProps) {
  const label = ariaLabel ?? (typeof title === "string" ? title : undefined);
  return (
    <section
      aria-label={label}
      className={[
        "rounded-md border border-line bg-surface overflow-hidden",
        "shadow-[0_1px_2px_rgba(80,60,30,0.08)]",
        className,
      ].join(" ")}
    >
      <header className="flex items-center justify-between gap-2 min-h-8 px-3 py-1.5 bg-titlebar border-b border-line">
        <div className="flex items-center gap-1.5 min-w-0 text-ink">
          <span className="shrink-0 text-ink-muted" aria-hidden="true">
            <IconGlyph kind={icon} />
          </span>
          <span className="truncate text-[12px] font-medium leading-tight">{title}</span>
        </div>
        {actions ? <div className="flex items-center gap-1 shrink-0">{actions}</div> : null}
      </header>
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}
