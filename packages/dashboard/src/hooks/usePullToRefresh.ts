import { useEffect, useRef, useState } from "react";

/**
 * Tiny touch-driven pull-to-refresh.
 *
 * Activates only when:
 *   - the user starts a touch with the page scrolled to the very top, AND
 *   - the touch moves a positive Y delta (downward),
 *
 * which mirrors the iOS native gesture so we don't fight scroll on a list
 * that's mid-scroll. When the pull distance exceeds `threshold` and the
 * user lifts, we invoke `onRefresh()` and surface a `refreshing` flag.
 *
 * Returns:
 *   - `pull`: current pull distance in px (clamped to threshold * 1.5).
 *   - `armed`: true once the pull has crossed `threshold`; UI uses this
 *     to flip the spinner from "pull to refresh" to "release to refresh".
 *   - `refreshing`: true between calling `onRefresh` and its resolution.
 *
 * The hook returns no JSX — pages compose their own indicator (a tiny
 * progress dot + label) and translate it via the returned `pull` value.
 *
 * The function does nothing when `enabled` is false.
 */
export interface PullToRefreshOptions {
  /** Distance in px past which a release triggers `onRefresh`. */
  threshold?: number;
  /** Disable the gesture (e.g., loading states). */
  enabled?: boolean;
}

export interface PullToRefreshState {
  pull: number;
  armed: boolean;
  refreshing: boolean;
}

const DEFAULT_THRESHOLD = 64;

export function usePullToRefresh(
  onRefresh: () => Promise<unknown> | undefined,
  options: PullToRefreshOptions = {},
): PullToRefreshState {
  const { threshold = DEFAULT_THRESHOLD, enabled = true } = options;

  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const tracking = useRef(false);
  const armedRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    const onTouchStart = (e: TouchEvent) => {
      // Only engage when the user is at the very top of the document.
      if ((window.scrollY || 0) > 0) return;
      const t = e.touches[0];
      if (!t) return;
      startY.current = t.clientY;
      tracking.current = true;
      armedRef.current = false;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!tracking.current || startY.current === null) return;
      const t = e.touches[0];
      if (!t) return;
      const dy = t.clientY - startY.current;
      if (dy <= 0) {
        // User reversed direction — abandon the gesture so they can scroll.
        setPull(0);
        return;
      }
      // Soft cap so the indicator doesn't run off the screen.
      const clamped = Math.min(dy, threshold * 1.5);
      setPull(clamped);
      armedRef.current = clamped >= threshold;
    };

    const finishGesture = async () => {
      if (!tracking.current) return;
      tracking.current = false;
      const wasArmed = armedRef.current;
      armedRef.current = false;
      startY.current = null;
      if (wasArmed) {
        setRefreshing(true);
        try {
          const r = onRefresh();
          if (r && typeof (r as Promise<unknown>).then === "function") {
            await r;
          }
        } finally {
          setRefreshing(false);
          setPull(0);
        }
      } else {
        setPull(0);
      }
    };

    const onTouchEnd = () => {
      void finishGesture();
    };

    const onTouchCancel = () => {
      tracking.current = false;
      armedRef.current = false;
      startY.current = null;
      setPull(0);
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd);
    window.addEventListener("touchcancel", onTouchCancel);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
      window.removeEventListener("touchcancel", onTouchCancel);
    };
  }, [enabled, threshold, onRefresh]);

  return {
    pull,
    armed: pull >= threshold,
    refreshing,
  };
}

/**
 * Pure helper, exported for tests: returns true when the pull distance is
 * past threshold and a release would fire onRefresh.
 */
export function shouldFireRefresh(pullDistance: number, threshold = DEFAULT_THRESHOLD): boolean {
  return pullDistance >= threshold;
}
