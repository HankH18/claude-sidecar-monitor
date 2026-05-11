import { formatRelative } from "../lib/time";

export interface ActivityLineProps {
  summary?: string | null;
  updatedAt?: string | null;
  className?: string;
}

/**
 * V2.B — one-line "what is this agent doing right now" digest.
 *
 * Backend derives a single sentence and a millisecond timestamp; we render
 * the sentence and a now-relative pill. Null → em-dash so an empty value
 * still occupies the row height (prevents layout shift when an update
 * lands while the user is scanning).
 */
export default function ActivityLine({ summary, updatedAt, className = "" }: ActivityLineProps) {
  const text = summary?.trim() || "—";
  const ts = updatedAt ? formatRelative(updatedAt) : "";
  return (
    <div
      className={`flex items-center gap-2 text-[11px] text-zinc-500 ${className}`}
      data-testid="activity-line"
    >
      <span className="truncate min-w-0 flex-1">{text}</span>
      {ts ? (
        <span
          className="shrink-0 tabular-nums text-zinc-600"
          title={updatedAt ? new Date(updatedAt).toLocaleString() : undefined}
        >
          {ts}
        </span>
      ) : null}
    </div>
  );
}
