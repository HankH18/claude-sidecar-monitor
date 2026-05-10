import { describe, expect, it } from "vitest";
import { formatRelative } from "./time";

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
