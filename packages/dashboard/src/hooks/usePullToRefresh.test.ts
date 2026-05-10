import { describe, expect, it } from "vitest";
import { shouldFireRefresh } from "./usePullToRefresh";

describe("shouldFireRefresh threshold", () => {
  it("returns false below the threshold", () => {
    expect(shouldFireRefresh(0)).toBe(false);
    expect(shouldFireRefresh(10)).toBe(false);
    expect(shouldFireRefresh(63)).toBe(false);
  });

  it("returns true at or above the threshold", () => {
    expect(shouldFireRefresh(64)).toBe(true);
    expect(shouldFireRefresh(120)).toBe(true);
  });

  it("respects an explicit threshold override", () => {
    expect(shouldFireRefresh(40, 30)).toBe(true);
    expect(shouldFireRefresh(40, 80)).toBe(false);
  });
});
