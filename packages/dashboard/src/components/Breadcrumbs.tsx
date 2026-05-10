import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * Compact breadcrumb strip.
 *
 * Each crumb is a tappable Link (≥44pt touch target via min-h-11) with the
 * tail crumb rendered as plain text since it represents the current page.
 * Separator is a hairline ›  glyph in zinc-600 — high enough contrast on
 * the dark surface to read at 11px.
 */

export interface Crumb {
  label: string;
  to?: string;
  /** Override the rendered label (e.g. with truncation). */
  display?: ReactNode;
}

export interface BreadcrumbsProps {
  items: Crumb[];
  className?: string;
}

export default function Breadcrumbs({ items, className = "" }: BreadcrumbsProps) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="breadcrumb" className={`text-xs ${className}`}>
      <ol className="flex items-center flex-wrap gap-x-1 text-zinc-500 -ml-1">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          const display = c.display ?? c.label;
          return (
            <li key={`${c.label}-${i}`} className="inline-flex items-center min-w-0">
              {c.to && !last ? (
                <Link
                  to={c.to}
                  className="inline-flex items-center min-h-11 px-1 text-emerald-300 hover:text-emerald-200 truncate max-w-[160px]"
                >
                  {display}
                </Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className="inline-flex items-center min-h-11 px-1 text-zinc-300 truncate max-w-[160px]"
                >
                  {display}
                </span>
              )}
              {!last ? (
                <span aria-hidden="true" className="text-zinc-600 px-0.5">
                  ›
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
