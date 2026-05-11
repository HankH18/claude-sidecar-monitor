import { useCallback, useEffect, useState } from "react";
import { ApiCallError, apiGet, withRetry } from "../api/client";
import { useMock } from "../api/mode";
import type { PermissionRequest, PermissionRequestList } from "../api/types";
import { useStream } from "./useStream";

/**
 * V2.D4 — list of pending permission requests, kept fresh via SSE.
 *
 * Refetches on:
 *   - mount
 *   - any incoming `permission_request` SSE event (the backend fires one
 *     whenever a new request is recorded, plus after a decision so the
 *     pending list shrinks).
 *   - explicit refresh() call (banner after a decision)
 *
 * Auth gating: `GET /api/permission-requests` requires the bearer token.
 * If the install has no api_secret yet (503) we surface the error and
 * render an empty list so the rest of the dashboard keeps working.
 */
export function usePermissionRequests(): {
  requests: PermissionRequest[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const mock = useMock();
  const [requests, setRequests] = useState<PermissionRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { lastEvent } = useStream({ kind: "permission_request" });

  const refresh = useCallback(async () => {
    if (mock) {
      setRequests([]);
      setLoading(false);
      return;
    }
    try {
      const res = await withRetry(() =>
        apiGet<PermissionRequestList>("/api/permission-requests?status=pending&limit=50"),
      );
      setRequests(res.requests);
      setError(null);
    } catch (e) {
      // 401 / 503 = no api_secret yet, treat as "no pending" so the rest
      // of the UI keeps working. Other errors surface as `error`.
      if (e instanceof ApiCallError && (e.status === 401 || e.status === 503)) {
        setRequests([]);
        setError(null);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, [mock]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    refresh().finally(() => {
      if (cancelled) return;
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // SSE-driven refresh. A burst (e.g. several pending requests landing
  // in the same tick) is fine — each refetch is idempotent and the list
  // shrinks naturally as decisions come in.
  useEffect(() => {
    if (!lastEvent || lastEvent.kind !== "permission_request") return;
    refresh();
  }, [lastEvent, refresh]);

  return { requests, loading, error, refresh };
}
