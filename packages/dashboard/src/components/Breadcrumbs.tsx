import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * Compact breadcrumb strip.
 *
 * Each crumb is a tappable Link (≥44pt touch target via min-h-11) with the
 * tail crumb rendered as plain text since it represents the current page.
 * Separator is a hairline ›  glyph in muted ink — high enough contrast on
 * the warm surface to read at 11px.
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
      <ol className="flex items-center flex-wrap gap-x-1 text-ink-muted -ml-1">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          const display = c.display ?? c.label;
          return (
            <li key={`${c.label}-${i}`} className="inline-flex items-center min-w-0">
              {c.to && !last ? (
                <Link
                  to={c.to}
                  className="inline-flex items-center min-h-11 px-1 text-teal hover:text-cta truncate max-w-[160px]"
                >
                  {display}
                </Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className="inline-flex items-center min-h-11 px-1 text-ink truncate max-w-[160px]"
                >
                  {display}
                </span>
              )}
              {!last ? (
                <span aria-hidden="true" className="text-ink-subtle px-0.5">
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
