import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import { mockSessions } from "../api/mock";
import { useMock } from "../api/mode";
import type { Session } from "../api/types";
import { useStream } from "./useStream";

interface StateResponse {
  sessions: Session[];
  lastEventAt: string;
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
    if (mock) {
      // Snapshot once. Subsequent updates flow via lastEvent below.
      setSessions([...mockSessions]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    apiGet<StateResponse>("/api/state")
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

  // Apply incoming session_update events.
  useEffect(() => {
    if (!lastEvent || lastEvent.kind !== "session_update") return;
    const sessionId = (lastEvent.session_id ?? (lastEvent.data.session_id as string)) || null;
    if (!sessionId) return;
    setSessions((prev) =>
      prev.map((s) =>
        s.session_id === sessionId
          ? {
              ...s,
              ...(lastEvent.data as Partial<Session>),
            }
          : s,
      ),
    );
  }, [lastEvent]);

  return { sessions, loading, error };
}
