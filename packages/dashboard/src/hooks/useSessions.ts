import { useEffect, useState } from "react";
import { apiGet, withRetry } from "../api/client";
import { mockSessions } from "../api/mock";
import { useMock } from "../api/mode";
import type { Session } from "../api/types";
import { useStream } from "./useStream";

interface StateResponse {
  sessions: Session[];
  // collector returns last_event_at; older builds returned lastEventAt.
  last_event_at?: string | null;
  lastEventAt?: string | null;
}

/** Fetches the session snapshot and applies session_update events live. */
export function useSessions(): {
  sessions: Session[];
  loading: boolean;
  error: string | null;
} {
  const mock = useMock();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { lastEvent } = useStream({ kind: "session_update" });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (mock) {
      // Snapshot once. Subsequent updates flow via lastEvent below.
      setSessions([...mockSessions]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    withRetry(() => apiGet<StateResponse>("/api/state"))
      .then((res) => {
        if (cancelled) return;
        setSessions(res.sessions);
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

  // Apply incoming session_update events. We merge the partial payload into
  // local state for low-latency; the next /api/state poll (or refresh) will
  // reconcile any drift.
  useEffect(() => {
    if (!lastEvent || lastEvent.kind !== "session_update") return;
    const sessionId = (lastEvent.session_id ?? (lastEvent.data.session_id as string)) || null;
    if (!sessionId) return;
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.session_id === sessionId);
      if (idx === -1) {
        // New session — if the event payload looks like a full Session, append it.
        const data = lastEvent.data as Partial<Session> & { session_id?: string };
        if (data.worktree_root && data.state && data.started_at) {
          return [...prev, data as Session];
        }
        return prev;
      }
      return prev.map((s) =>
        s.session_id === sessionId
          ? {
              ...s,
              ...(lastEvent.data as Partial<Session>),
            }
          : s,
      );
    });
  }, [lastEvent]);

  return { sessions, loading, error };
}
