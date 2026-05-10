import { useEffect, useRef, useState } from "react";
import { useStream } from "../hooks/useStream";
import { useToast } from "./Toast";

/**
 * Sticky-below-the-header banner that becomes actionable when the SSE
 * stream is unhappy.
 *
 * UX rules:
 *   - "connecting" / "reconnecting": invisible until 10s of consecutive
 *     non-`connected` time accumulates, so a fast retry doesn't show a
 *     scary banner.
 *   - "disconnected" past 10s: visible with a "retry now" affordance.
 *   - Transitions emit toasts so the user gets a heads-up even if they
 *     had scrolled past the banner.
 *
 * The retry path simply calls `window.location.reload()` — the SSE client
 * in `stream.ts` reconnects on its own, so this is the heaviest hammer
 * the user has and the only one that's deterministic across browsers
 * with stale EventSource state.
 */

const SHOW_AFTER_MS = 10_000;

export default function ConnectionBanner() {
  const { status } = useStream();
  const { push } = useToast();
  const [show, setShow] = useState(false);
  const lostSinceRef = useRef<number | null>(null);
  const prevStatusRef = useRef(status);

  // Track when the connection first went bad so we can defer showing the
  // banner. Reset when we recover.
  useEffect(() => {
    if (status === "connected") {
      lostSinceRef.current = null;
      setShow(false);
      return;
    }
    if (lostSinceRef.current === null) {
      lostSinceRef.current = Date.now();
    }
    // After SHOW_AFTER_MS has elapsed since first loss, reveal.
    const id = setTimeout(() => {
      if (lostSinceRef.current && Date.now() - lostSinceRef.current >= SHOW_AFTER_MS) {
        setShow(true);
      }
    }, SHOW_AFTER_MS);
    return () => clearTimeout(id);
  }, [status]);

  // Toasts on transition.
  useEffect(() => {
    const prev = prevStatusRef.current;
    if (prev !== status) {
      if (status === "connected" && (prev === "reconnecting" || prev === "disconnected")) {
        push({
          message: "Back online — stream reconnected.",
          variant: "success",
          durationMs: 2_500,
        });
      } else if (status === "disconnected" && prev === "connected") {
        push({
          message: "Lost connection to collector.",
          variant: "error",
          durationMs: 4_000,
        });
      }
      prevStatusRef.current = status;
    }
  }, [status, push]);

  if (!show || status === "connected") return null;

  const verb =
    status === "reconnecting"
      ? "Reconnecting"
      : status === "connecting"
        ? "Connecting"
        : "Lost connection";

  return (
    <div
      role="alert"
      aria-live="polite"
      className="sticky top-[88px] z-[5] mx-3 my-2 rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs px-3 py-2 flex items-center justify-between gap-2"
      data-testid="connection-banner"
    >
      <span className="truncate">{verb} to collector. Stream is paused — data may be stale.</span>
      <button
        type="button"
        onClick={() => {
          if (typeof window !== "undefined") window.location.reload();
        }}
        className="shrink-0 inline-flex items-center justify-center min-h-9 px-3 rounded border border-amber-500/50 hover:bg-amber-500/20 text-amber-100 text-[11px] font-medium"
      >
        Retry now
      </button>
    </div>
  );
}
