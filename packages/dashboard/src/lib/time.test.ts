import { describe, expect, it } from "vitest";
import { formatDuration, formatLocalShort, formatRelative } from "./time";

const NOW = Date.parse("2026-05-10T12:00:00Z");

describe("formatRelative", () => {
  it("renders 'just now' for sub-5s differences", () => {
    expect(formatRelative(NOW - 0, NOW)).toBe("just now");
    expect(formatRelative(NOW - 4_000, NOW)).toBe("just now");
  });

  it("renders 'Ns ago' between 5s and 60s", () => {
    expect(formatRelative(NOW - 12_000, NOW)).toBe("12s ago");
    expect(formatRelative(NOW - 59_000, NOW)).toBe("59s ago");
  });

  it("renders 'Nm ago' between 60s and 60min", () => {
    expect(formatRelative(NOW - 60_000, NOW)).toBe("1m ago");
    expect(formatRelative(NOW - 3 * 60_000, NOW)).toBe("3m ago");
    expect(formatRelative(NOW - 59 * 60_000, NOW)).toBe("59m ago");
  });

  it("renders 'Nh ago' between 1h and 24h on the same calendar day", () => {
    // 2 hours back from noon = 10am same day
    expect(formatRelative(NOW - 2 * 60 * 60_000, NOW)).toBe("2h ago");
  });

  it("renders 'yesterday HH:MMp' for 24-48h differences", () => {
    // Exactly 26h before NOW — guaranteed to land in the 24-48h window
    // regardless of local TZ.
    const yesterday = NOW - 26 * 60 * 60_000;
    const result = formatRelative(yesterday, NOW);
    expect(result).toMatch(/^yesterday /);
    expect(result).toMatch(/\d{1,2}:\d{2}[ap]$/);
  });

  it("renders 'Mon D' for older same-year dates", () => {
    // Pick a date that's clearly past the 48h "yesterday" window.
    const earlierMay = Date.parse("2026-05-04T18:00:00Z");
    const result = formatRelative(earlierMay, NOW);
    // Allow ±1 day to absorb local TZ shift on the test runner.
    expect(result).toMatch(/May [3-5]/);
  });

  it("renders 'Mon D, YYYY' across year boundaries", () => {
    // Pick a time mid-day UTC so local-TZ-based formatting still lands on
    // the same calendar day across all CI machines.
    const lastDecember = Date.parse("2024-12-25T18:00:00Z");
    const result = formatRelative(lastDecember, NOW);
    expect(result).toMatch(/Dec 2[5-6], 2024/);
  });

  it("returns empty string for unparseable input", () => {
    expect(formatRelative("nope", NOW)).toBe("");
    expect(formatRelative(null, NOW)).toBe("");
    expect(formatRelative(undefined, NOW)).toBe("");
  });
});

describe("formatDuration", () => {
  it("returns '0s' for zero or negative input", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(-5)).toBe("0s");
  });

  it("formats seconds under a minute", () => {
    expect(formatDuration(1)).toBe("1s");
    expect(formatDuration(45)).toBe("45s");
  });

  it("formats minutes + seconds under 10 minutes", () => {
    expect(formatDuration(60)).toBe("1m");
    expect(formatDuration(133)).toBe("2m 13s");
    expect(formatDuration(540)).toBe("9m");
  });

  it("drops seconds once we cross 10 minutes", () => {
    expect(formatDuration(10 * 60)).toBe("10m");
    expect(formatDuration(14 * 60 + 30)).toBe("14m");
    expect(formatDuration(59 * 60 + 59)).toBe("59m");
  });

  it("formats hours + minutes under a day", () => {
    expect(formatDuration(3_600)).toBe("1h");
    expect(formatDuration(3_600 + 4 * 60)).toBe("1h 4m");
    expect(formatDuration(23 * 3_600 + 59 * 60)).toBe("23h 59m");
  });

  it("formats days + hours past a day", () => {
    expect(formatDuration(24 * 3_600)).toBe("1d");
    expect(formatDuration(3 * 86_400 + 2 * 3_600)).toBe("3d 2h");
  });

  it("handles non-finite input gracefully", () => {
    expect(formatDuration(Number.NaN)).toBe("0s");
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe("0s");
  });
});

describe("formatLocalShort", () => {
  it("returns a non-empty string for valid ISO input", () => {
    const out = formatLocalShort(new Date(NOW).toISOString(), NOW);
    expect(out).not.toBe("");
    // Same-day → just the time. Should contain ":" and AM/PM.
    expect(out).toMatch(/\d{1,2}:\d{2}\s(AM|PM)/);
  });

  it("returns empty string for null / undefined / unparseable input", () => {
    expect(formatLocalShort(null, NOW)).toBe("");
    expect(formatLocalShort(undefined, NOW)).toBe("");
    expect(formatLocalShort("nope", NOW)).toBe("");
    expect(formatLocalShort("", NOW)).toBe("");
  });

  it("prefixes weekday for times in the past week (not today)", () => {
    // 3 days back from NOW.
    const past = NOW - 3 * 86_400_000;
    const out = formatLocalShort(past, NOW);
    expect(out).toMatch(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) /);
    expect(out).toMatch(/\d{1,2}:\d{2}\s(AM|PM)$/);
  });

  it("falls back to 'Mon D' format for older same-year dates", () => {
    // 10 days back from NOW — outside the weekday window, inside the same year.
    const older = NOW - 10 * 86_400_000;
    const out = formatLocalShort(older, NOW);
    // Should include a month abbrev. Allow ±1 day for local TZ.
    expect(out).toMatch(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}/);
    expect(out).toMatch(/\d{1,2}:\d{2}\s(AM|PM)$/);
  });

  it("accepts a Date object", () => {
    const d = new Date(NOW);
    expect(formatLocalShort(d, NOW)).toMatch(/\d{1,2}:\d{2}\s(AM|PM)/);
  });
});
