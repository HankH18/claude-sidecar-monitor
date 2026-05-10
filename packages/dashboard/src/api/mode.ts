/**
 * Single source of truth for the mock vs. real-backend toggle.
 *
 * Default is **live** (mock=false) — the dashboard talks to the collector
 * at /api/* and /stream out of the box.
 *
 * Override in three ways:
 *   - VITE_USE_MOCK=true (vite env, build-time)
 *   - window.__CSM_USE_MOCK__ = true (runtime, e.g. dev console)
 *   - test code can call setUseMockOverride(true)
 */

let runtimeOverride: boolean | null = null;

export function setUseMockOverride(value: boolean | null): void {
  runtimeOverride = value;
}

export function useMock(): boolean {
  if (runtimeOverride !== null) return runtimeOverride;
  if (typeof window !== "undefined") {
    const w = window as unknown as { __CSM_USE_MOCK__?: boolean };
    if (typeof w.__CSM_USE_MOCK__ === "boolean") return w.__CSM_USE_MOCK__;
  }
  // Vite env var. Default false (live).
  const env =
    typeof import.meta !== "undefined" &&
    (import.meta as unknown as { env?: Record<string, string> }).env;
  if (env && env.VITE_USE_MOCK === "true") return true;
  return false;
}
