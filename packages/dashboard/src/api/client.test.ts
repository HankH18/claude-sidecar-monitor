import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiCallError, withRetry } from "./client";

describe("withRetry", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns immediately on first success", async () => {
    const fn = vi.fn(async () => "ok");
    const out = await withRetry(fn, { retries: 2, baseDelayMs: 1 });
    expect(out).toBe("ok");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("retries on transient errors and resolves once one succeeds", async () => {
    let attempt = 0;
    const fn = vi.fn(async () => {
      attempt += 1;
      if (attempt < 3) throw new Error("transient");
      return "yay";
    });
    const out = await withRetry(fn, { retries: 3, baseDelayMs: 1 });
    expect(out).toBe("yay");
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("throws after exhausting attempts", async () => {
    const fn = vi.fn(async () => {
      throw new Error("never works");
    });
    await expect(withRetry(fn, { retries: 2, baseDelayMs: 1 })).rejects.toThrow(/never works/);
    // Initial call + 2 retries = 3.
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("does not retry on 4xx ApiCallError (e.g. 404)", async () => {
    const fn = vi.fn(async () => {
      throw new ApiCallError(404, "not_found", "missing");
    });
    await expect(withRetry(fn, { retries: 5, baseDelayMs: 1 })).rejects.toBeInstanceOf(
      ApiCallError,
    );
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("does retry on 5xx ApiCallError", async () => {
    let n = 0;
    const fn = vi.fn(async () => {
      n += 1;
      if (n < 2) throw new ApiCallError(503, "unavailable", "down");
      return "back";
    });
    const out = await withRetry(fn, { retries: 3, baseDelayMs: 1 });
    expect(out).toBe("back");
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("uses default options when none given", async () => {
    const fn = vi.fn(async () => "default");
    const out = await withRetry(fn);
    expect(out).toBe("default");
  });
});
