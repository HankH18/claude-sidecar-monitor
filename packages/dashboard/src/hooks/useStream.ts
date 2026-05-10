import { useEffect, useRef, useState } from "react";
import { mockStream } from "../api/mock";
import { useMock } from "../api/mode";
import { openStream } from "../api/stream";
import type { StreamEvent, StreamEventKind } from "../api/types";

interface UseStreamOptions {
  /** Only receive events with this kind. */
  kind?: StreamEventKind;
  /** Cap how many events to retain. Default 50. */
  limit?: number;
}

/**
 * Subscribes to either the real /stream SSE endpoint or the mock generator,
 * exposes the latest event + a rolling buffer.
 *
 * Components that just want the latest event for a session should use
 * `lastEvent`. Pages with a timeline can read `events`.
 */
export function useStream(options: UseStreamOptions = {}): {
  lastEvent: StreamEvent | null;
  events: StreamEvent[];
} {
  const { kind, limit = 50 } = options;
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const lastRef = useRef<StreamEvent | null>(null);
  const [lastEvent, setLastEvent] = useState<StreamEvent | null>(null);
  const mock = useMock();

  useEffect(() => {
    const handler = (e: StreamEvent) => {
      if (kind && e.kind !== kind) return;
      lastRef.current = e;
      setLastEvent(e);
      setEvents((prev) => {
        const next = [...prev, e];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    };

    if (mock) {
      const ctl = mockStream(handler);
      return () => ctl.close();
    }
    const ctl = openStream(handler);
    return () => ctl.close();
  }, [mock, kind, limit]);

  return { lastEvent, events };
}
