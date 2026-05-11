import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiCallError, apiGet, withRetry } from "../api/client";
import type { PermissionRequest, PermissionRequestList } from "../api/types";
import PermissionSheet from "../components/PermissionSheet";

/**
 * V2.D4 — `/permissions/:id` deep-link route.
 *
 * The ntfy push opens this URL with a signed token (for the deep-link
 * auth path); the dashboard immediately opens the PermissionSheet for
 * that request id.
 *
 * Fallback behaviour:
 *   - If the request is no longer pending (decided / expired): show a
 *     "no longer pending" message + a back-to-Live link.
 *   - If it doesn't exist (404): same.
 */
export default function PermissionDeepLink() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [request, setRequest] = useState<PermissionRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        // No GET-by-id endpoint yet, so we read the pending list and pick
        // the matching row. TODO(backend): expose
        // GET /api/permission-requests/:id so we don't have to scan.
        const res = await withRetry(() =>
          apiGet<PermissionRequestList>("/api/permission-requests?status=pending&limit=500"),
        );
        if (cancelled) return;
        const match = res.requests.find((r) => String(r.id) === id);
        if (!match) {
          setError("Request is no longer pending.");
          setRequest(null);
        } else {
          setRequest(match);
        }
        setLoading(false);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiCallError && (e.status === 401 || e.status === 503)) {
          setError("Dashboard is not authorised — run `csm install` to set up the API secret.");
        } else {
          setError((e as Error).message);
        }
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <div className="h-5 w-40 rounded bg-zinc-800/60 animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-zinc-800/40 animate-pulse" />
      </div>
    );
  }

  if (error || !request) {
    return (
      <div className="space-y-3">
        <h1 className="text-lg font-semibold text-zinc-100">Permission request</h1>
        <p className="text-sm text-zinc-500">{error ?? "Not found."}</p>
        <Link
          to="/"
          className="inline-flex items-center min-h-11 px-3 rounded-md text-xs text-emerald-300 hover:text-emerald-200 border border-zinc-800 hover:bg-zinc-900/40"
        >
          ← back to Live
        </Link>
      </div>
    );
  }

  return (
    <PermissionSheet
      request={request}
      onClose={() => navigate("/")}
      onDecided={() => navigate("/")}
    />
  );
}
