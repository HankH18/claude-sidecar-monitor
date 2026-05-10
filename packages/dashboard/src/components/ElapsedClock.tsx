import { useEffect, useState } from "react";

interface ElapsedClockProps {
  /** ISO timestamp of session start (or last activity). */
  since: string;
  /** When false, the clock freezes. Use for done/hung sessions. */
  live?: boolean;
  className?: string;
}

function format(ms: number): string {
  const safeMs = ms < 0 ? 0 : ms;
  const totalSec = Math.floor(safeMs / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h >= 1) {
    return `${h}:${String(m).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** 1 Hz client-side counter rendering elapsed time since `since`. */
export default function ElapsedClock({ since, live = true, className = "" }: ElapsedClockProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);

  const start = Date.parse(since);
  const elapsed = Number.isNaN(start) ? 0 : now - start;
  return (
    <span
      className={`font-mono tabular-nums ${className}`}
      aria-label={`elapsed ${format(elapsed)}`}
    >
      {format(elapsed)}
    </span>
  );
}
