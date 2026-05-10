/**
 * Tiny zero-dependency time formatter.
 *
 * Goal: now-relative phrasing for at-a-glance reading on a phone, without
 * dragging in `date-fns` or `dayjs` (kilobytes saved + no transitive deps).
 *
 * Boundaries (tuned for the dashboard's "is this fresh?" question):
 *
 *   < 5s        → "just now"
 *   < 60s       → "12s ago"
 *   < 60min     → "3m ago"
 *   < 24h       → "5h ago"
 *   yesterday   → "yesterday 4:01p"
 *   this year   → "May 8"
 *   older       → "May 8, 2024"
 *
 * Returns an empty string for unparseable input — callers should guard
 * upstream when "(unknown)" is preferable.
 */

/** Lowercase 12-hour time ("4:01p"). */
function timeOfDay(d: Date): string {
  let h = d.getHours();
  const m = d.getMinutes();
  const ampm = h >= 12 ? "p" : "a";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${String(m).padStart(2, "0")}${ampm}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Returns a now-relative formatted string for `iso` (ISO timestamp or epoch ms). */
export function formatRelative(
  iso: string | number | Date | null | undefined,
  now?: number,
): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const t = iso instanceof Date ? iso.getTime() : typeof iso === "number" ? iso : Date.parse(iso);
  if (Number.isNaN(t)) return "";

  const ref = now ?? Date.now();
  const diff = ref - t;

  if (diff < 0) {
    // Future timestamp — fall through to the absolute-date branches.
    return absoluteFormat(new Date(t), new Date(ref));
  }

  if (diff < 5_000) return "just now";
  if (diff < 60_000) {
    const s = Math.floor(diff / 1_000);
    return `${s}s ago`;
  }
  if (diff < 60 * 60_000) {
    const m = Math.floor(diff / 60_000);
    return `${m}m ago`;
  }
  if (diff < 24 * 60 * 60_000) {
    // Use calendar "today" — if we crossed midnight but it's still <24h, we
    // still want "Xh ago" not "yesterday".
    const target = new Date(t);
    const today = new Date(ref);
    if (
      target.getFullYear() === today.getFullYear() &&
      target.getMonth() === today.getMonth() &&
      target.getDate() === today.getDate()
    ) {
      const h = Math.floor(diff / (60 * 60_000));
      return `${h}h ago`;
    }
    // Crossed midnight but <24h ago — treat as "yesterday HH:MMp".
    return `yesterday ${timeOfDay(target)}`;
  }

  return absoluteFormat(new Date(t), new Date(ref));
}

function absoluteFormat(target: Date, ref: Date): string {
  // "yesterday" once we're between 24h–48h.
  const dayMs = 24 * 60 * 60_000;
  const diff = ref.getTime() - target.getTime();
  if (diff >= dayMs && diff < 2 * dayMs) {
    return `yesterday ${timeOfDay(target)}`;
  }
  const sameYear = target.getFullYear() === ref.getFullYear();
  const month = MONTHS[target.getMonth()];
  if (sameYear) return `${month} ${target.getDate()}`;
  return `${month} ${target.getDate()}, ${target.getFullYear()}`;
}
