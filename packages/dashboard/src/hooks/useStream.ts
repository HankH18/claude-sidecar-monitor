import { useEffect, useRef, useState } from "react";
import { mockStream } from "../api/mock";
import { useMock } from "../api/mode";
import { openStream } from "../api/stream";
import type { StreamEvent, StreamEventKind } from "../api/types";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

interface UseStreamOptions {
  /** Only receive events with this kind. */
  kind?: StreamEventKind;
  /** Cap how many events to retain. Default 50. */
  limit?: number;
}

export interface UseStreamResult {
  lastEvent: StreamEvent | null;
  events: StreamEvent[];
  status: ConnectionStatus;
  lastEventAt: number | null;
}

/**
 * Subscribes to either the real /stream SSE endpoint or the mock generator,
 * exposes the latest event, a rolling buffer, and a coarse connection status.
 *
 * Components that just want the latest event for a session should use
 * `lastEvent`. Pages with a timeline can read `events`. The header dot reads
 * `status` + `lastEventAt`.
 */
export function useStream(options: UseStreamOptions = {}): UseStreamResult {
  const { kind, limit = 50 } = options;
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const lastRef = useRef<StreamEvent | null>(null);
  const [lastEvent, setLastEvent] = useState<StreamEvent | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const mock = useMock();

  useEffect(() => {
    const handler = (e: StreamEvent) => {
      setLastEventAt(Date.now());
      if (kind && e.kind !== kind) return;
      lastRef.current = e;
      setLastEvent(e);
      setEvents((prev) => {
        const next = [...prev, e];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    };

    if (mock) {
      setStatus("connected");
      const ctl = mockStream(handler);
      return () => ctl.close();
    }
    setStatus("connecting");
    const ctl = openStream(handler, {
      onOpen: () => setStatus("connected"),
      onError: () => {
        setStatus((prev) => (prev === "connected" ? "reconnecting" : "disconnected"));
      },
    });
    return () => ctl.close();
  }, [mock, kind, limit]);

  return { lastEvent, events, status, lastEventAt };
}
