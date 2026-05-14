import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, withRetry } from "../api/client";
import { useMock } from "../api/mode";
import type { DashboardKpis } from "../api/types";
import { useStream } from "./useStream";

// Coalesce refetches when many SSE events arrive in a short burst. The
// dashboard endpoint runs ~6 indexed SELECTs — cheap, but no point
// running it 10× in one second when one fetch covers them all.
const REFETCH_DEBOUNCE_MS = 750;

/**
 * Mock fallback so the dashboard renders something during dev/SSR tests
 * when `useMock()` is on. The shape mirrors what the collector returns
 * for an empty / quiet system.
 */
function emptyKpis(): DashboardKpis {
  return {
    live_sessions: 0,
    hung_sessions: 0,
    state_counts: {
      running: 0,
      tool: 0,
      waiting_user: 0,
      idle: 0,
      hung: 0,
      done: 0,
    },
    total_tokens_today: 0,
    total_tokens_last_hour: 0,
    events_last_hour: 0,
    events_per_minute_60m: [],
    top_models_today: [],
    as_of: new Date().toISOString(),
  };
}

/** Fetches /api/dashboard and refetches on session/event SSE bursts. */
export function useDashboard(): {
  kpis: DashboardKpis | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
} {
  const mock = useMock();
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { lastEvent } = useStream();

  const refetch = useCallback(async () => {
    if (mock) {
      setKpis(emptyKpis());
      return;
    }
    try {
      const res = await withRetry(() => apiGet<DashboardKpis>("/api/dashboard"));
      setKpis(res);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [mock]);

  // Initial load.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (mock) {
      setKpis(emptyKpis());
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    withRetry(() => apiGet<DashboardKpis>("/api/dashboard"))
      .then((res) => {
        if (cancelled) return;
        setKpis(res);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mock]);

  // Refetch on any event that would change KPIs — session state changes,
  // raw events (rolls the sparkline), settings changes. Debounced so a
  // burst of activity doesn't fan into a burst of GETs.
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    if (mock || !lastEvent) return;
    const triggers = new Set(["session_update", "event", "settings_changed"]);
    if (!triggers.has(lastEvent.kind)) return;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      refetch();
    }, REFETCH_DEBOUNCE_MS);
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [mock, lastEvent, refetch]);

  return { kpis, loading, error, refetch };
}
