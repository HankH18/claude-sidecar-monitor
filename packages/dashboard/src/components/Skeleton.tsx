/**
 * Content-shaped loading skeletons.
 *
 * Generic `<Skeleton>` is a pulsing block; specific compositions
 * (`SessionRowSkeleton`, `ProjectSummarySkeleton`) mirror the shape of the
 * real content so the layout doesn't reflow on data arrival.
 */

interface SkeletonProps {
  className?: string;
  /** Override the role; defaults to a presentation-only block. */
  ariaLabel?: string;
}

export default function Skeleton({ className = "", ariaLabel }: SkeletonProps) {
  return (
    <div
      aria-hidden={ariaLabel ? undefined : "true"}
      aria-label={ariaLabel}
      className={`animate-pulse rounded bg-zinc-800/60 ${className}`}
    />
  );
}

/**
 * One row mirroring SessionRow on Overview / ProjectDetail:
 * [pill] [agent_type / model · elapsed]                     [tokens]
 */
export function SessionRowSkeleton() {
  return (
    <li className="flex items-center gap-2 px-3 py-3">
      {/* state pill — circle then short label */}
      <Skeleton className="h-5 w-16 rounded-full" />
      <div className="flex-1 min-w-0 space-y-1.5">
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-2.5 w-1/2" />
      </div>
      <div className="text-right space-y-1.5 shrink-0">
        <Skeleton className="h-3 w-14 ml-auto" />
        <Skeleton className="h-2.5 w-10 ml-auto" />
      </div>
    </li>
  );
}

/** A skeleton list mirroring an Overview project group. */
export function ProjectGroupSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3.5 w-1/3" />
        <Skeleton className="h-3 w-16" />
      </div>
      <ul className="divide-y divide-zinc-800 rounded-md border border-zinc-800">
        {Array.from({ length: rows }).map((_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: pure presentational placeholders
          <SessionRowSkeleton key={i} />
        ))}
      </ul>
    </section>
  );
}

/** Skeleton mirroring the ProjectDetail summary card grid (2x2). */
export function ProjectSummarySkeleton() {
  return (
    <section className="grid grid-cols-2 gap-3 rounded-md border border-zinc-800 p-3">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className="h-2.5 w-12" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </section>
  );
}

/** Skeleton mirroring a tree of N rows. */
export function TreeSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="rounded-md border border-zinc-800 p-2 space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: pure presentational placeholders
          key={i}
          className="flex items-center gap-2"
          style={{ paddingLeft: `${(i % 3) * 16}px` }}
        >
          <Skeleton className="h-3 w-3 shrink-0 rounded-sm" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-3 flex-1 max-w-[40%]" />
          <Skeleton className="h-3 w-12" />
        </div>
      ))}
    </div>
  );
}
