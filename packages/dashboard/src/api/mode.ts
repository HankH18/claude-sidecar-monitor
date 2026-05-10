/**
 * Single source of truth for the mock vs. real-backend toggle.
 *
 * v0.1 default is mock=true because the collector backend is in flight.
 * Override in three ways:
 *   - VITE_USE_MOCK=false (vite env, build-time)
 *   - window.__CSM_USE_MOCK__ = false (runtime, e.g. dev console)
 *   - test code can call setUseMockOverride(false)
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
  // Vite env var. Default true.
  const env =
    typeof import.meta !== "undefined" &&
    (import.meta as unknown as { env?: Record<string, string> }).env;
  if (env && env.VITE_USE_MOCK === "false") return false;
  return true;
}
