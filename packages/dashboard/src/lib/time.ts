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

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * Short local-TZ time format suitable for the per-row stats line.
 * Examples: "Mon 3:24 PM", "Fri 11:08 AM".
 *
 * Same-day inputs drop the weekday prefix → "3:24 PM" to save horizontal
 * space on the (very tight) 380px mobile target. Older-than-a-week inputs
 * fall back to "May 8 3:24 PM" so the user isn't left guessing what day
 * "Mon" referred to.
 *
 * Returns an empty string for unparseable input — matches `formatRelative`.
 */
export function formatLocalShort(
  iso: string | number | Date | null | undefined,
  now?: number,
): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const t = iso instanceof Date ? iso.getTime() : typeof iso === "number" ? iso : Date.parse(iso);
  if (Number.isNaN(t)) return "";

  const target = new Date(t);
  const ref = new Date(now ?? Date.now());

  let h = target.getHours();
  const m = target.getMinutes();
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12;
  if (h === 0) h = 12;
  const hm = `${h}:${String(m).padStart(2, "0")} ${ampm}`;

  // Same calendar day → just the time.
  if (
    target.getFullYear() === ref.getFullYear() &&
    target.getMonth() === ref.getMonth() &&
    target.getDate() === ref.getDate()
  ) {
    return hm;
  }

  const diff = Math.abs(ref.getTime() - target.getTime());
  const weekMs = 7 * 24 * 60 * 60_000;
  if (diff < weekMs) {
    return `${WEEKDAYS[target.getDay()]} ${hm}`;
  }

  const sameYear = target.getFullYear() === ref.getFullYear();
  const month = MONTHS[target.getMonth()];
  const date = `${month} ${target.getDate()}`;
  if (sameYear) return `${date} ${hm}`;
  return `${date}, ${target.getFullYear()} ${hm}`;
}

/**
 * Compact duration formatter for elapsed time displays.
 *
 *   < 60s     → "12s"
 *   < 60min   → "3m 4s" (drops seconds once we cross 10 min: "14m")
 *   < 24h     → "1h 12m"
 *   ≥ 24h     → "3d 2h"
 *
 * Accepts seconds (number) — callers compute the diff themselves.
 * Returns "0s" for 0 and negative inputs (clamped).
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3_600) {
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (m >= 10 || rem === 0) return `${m}m`;
    return `${m}m ${rem}s`;
  }
  if (s < 86_400) {
    const h = Math.floor(s / 3_600);
    const m = Math.floor((s % 3_600) / 60);
    if (m === 0) return `${h}h`;
    return `${h}h ${m}m`;
  }
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3_600);
  if (h === 0) return `${d}d`;
  return `${d}d ${h}h`;
}
