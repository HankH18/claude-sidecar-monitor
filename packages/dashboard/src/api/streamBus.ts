import type { StreamEvent } from "./types";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

export type StreamHandler = (e: StreamEvent) => void;
export type StatusHandler = (s: ConnectionStatus) => void;

/**
 * Singleton SSE fan-out.
 *
 * Browsers cap concurrent HTTP/1.1 connections per origin at 6. Every
 * `useStream` hook instance previously opened its own EventSource — so a
 * page with N ProjectTreeSections + a few other live-data hooks would
 * starve the connection pool, hang asset loads, and freeze navigation.
 *
 * The bus keeps exactly ONE EventSource alive while there's at least one
 * subscriber, fanning incoming events out to all handlers in process.
 * When the last subscriber unsubscribes, the EventSource closes; the
 * next subscriber re-opens it.
 *
 * Reconnect on transport errors mirrors the previous per-hook behaviour
 * (handled by EventSource's built-in retry plus a manual fallback when
 * the source ends up in CLOSED state).
 */

const STREAM_URL = "/stream";
const RECONNECT_DELAY_MS = 2000;

let source: EventSource | null = null;
let reconnectTimer: number | null = null;
let status: ConnectionStatus = "disconnected";

const eventHandlers: Set<StreamHandler> = new Set();
const statusHandlers: Set<StatusHandler> = new Set();

function setStatus(s: ConnectionStatus): void {
  if (status === s) return;
  status = s;
  for (const h of statusHandlers) h(s);
}

function connect(): void {
  if (typeof EventSource === "undefined") {
    setStatus("disconnected");
    return;
  }
  if (source) return; // Already connected (or connecting).

  setStatus(status === "connected" ? "reconnecting" : "connecting");
  source = new EventSource(STREAM_URL);

  source.onopen = () => {
    setStatus("connected");
  };

  source.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data) as StreamEvent;
      // Copy the set so a handler unsubscribing mid-iteration doesn't
      // skip a sibling handler.
      for (const h of Array.from(eventHandlers)) {
        try {
          h(parsed);
        } catch (err) {
          console.error("streamBus: handler threw", err);
        }
      }
    } catch (err) {
      console.warn("streamBus: failed to parse message", err, msg.data);
    }
  };

  source.onerror = () => {
    setStatus("reconnecting");
    // EventSource will auto-retry while readyState === CONNECTING. If it
    // ended up CLOSED, schedule a manual reconnect (matches the old
    // openStream behaviour).
    if (source?.readyState === EventSource.CLOSED && eventHandlers.size > 0) {
      source = null;
      if (reconnectTimer === null) {
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, RECONNECT_DELAY_MS);
      }
    }
  };
}

function disconnectIfIdle(): void {
  if (eventHandlers.size > 0 || statusHandlers.size > 0) return;
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  source?.close();
  source = null;
  setStatus("disconnected");
}

export function subscribeEvents(handler: StreamHandler): () => void {
  eventHandlers.add(handler);
  if (!source) connect();
  return () => {
    eventHandlers.delete(handler);
    disconnectIfIdle();
  };
}

export function subscribeStatus(handler: StatusHandler): () => void {
  statusHandlers.add(handler);
  // Replay current status synchronously so the new subscriber doesn't
  // miss the "connected" edge that already happened.
  handler(status);
  if (!source && eventHandlers.size === 0) connect();
  return () => {
    statusHandlers.delete(handler);
    disconnectIfIdle();
  };
}

/** Test-only helper — force tear-down so vitest isolation works. */
export function _resetForTests(): void {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  source?.close();
  source = null;
  status = "disconnected";
  eventHandlers.clear();
  statusHandlers.clear();
}
