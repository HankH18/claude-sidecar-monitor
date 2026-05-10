import type { StreamEvent, StreamEventKind } from "./types";

export type StreamHandler = (event: StreamEvent) => void;

export interface StreamController {
  close(): void;
}

interface OpenStreamOptions {
  url?: string;
  reconnectDelayMs?: number;
  onOpen?: () => void;
  onError?: (e: Event) => void;
}

/**
 * Subscribe to the collector's `/stream` SSE endpoint with auto-reconnect.
 *
 * The browser's EventSource auto-reconnects on transport errors; we add a
 * manual fallback so we can swap stream URLs (e.g., changing tailnet host).
 */
export function openStream(
  handler: StreamHandler,
  options: OpenStreamOptions = {},
): StreamController {
  const { url = "/stream", reconnectDelayMs = 2000, onOpen, onError } = options;

  let closed = false;
  let source: EventSource | null = null;
  let reconnectTimer: number | null = null;

  const connect = () => {
    if (closed) return;
    source = new EventSource(url);
    source.onopen = () => {
      onOpen?.();
    };
    source.onerror = (e) => {
      onError?.(e);
      // EventSource will retry itself when readyState is CONNECTING. If it
      // closed, schedule a manual reconnect.
      if (source?.readyState === EventSource.CLOSED && !closed) {
        source = null;
        reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
      }
    };
    source.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as StreamEvent;
        handler(parsed);
      } catch (err) {
        console.warn("stream: failed to parse message", err, msg.data);
      }
    };
  };

  connect();

  return {
    close() {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      source?.close();
      source = null;
    },
  };
}

/** Filter helper used by hooks. */
export function isKind<K extends StreamEventKind>(
  e: StreamEvent,
  kind: K,
): e is StreamEvent & { kind: K } {
  return e.kind === kind;
}
