import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/**
 * Tiny inline toast system.
 *
 * No third-party toast library — the bar for adding a dependency here is
 * "the inline implementation would be >150 lines of subtle behavior".
 * Toasts in this app are short status pings (save success, connection
 * blip), not interactive surfaces with focus management or undo, so a
 * minimal queue + auto-dismiss covers the cases.
 *
 * Public surface:
 *   - <ToastProvider> — mount once near the root.
 *   - useToast() — returns { push, dismiss }.
 *
 * Variants drive color only; the shape (top-right card, ≥44pt min height,
 * fade/slide-in) is identical so screen reader output is consistent.
 */

export type ToastVariant = "success" | "error" | "info";

export interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
  /** Auto-dismiss after this many ms. 0 disables. */
  durationMs: number;
}

interface PushArgs {
  message: string;
  variant?: ToastVariant;
  durationMs?: number;
}

interface ToastContextValue {
  toasts: Toast[];
  push(args: PushArgs): string;
  dismiss(id: string): void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** Module-level counter so generated ids stay stable across renders/tests. */
let _toastCounter = 0;
function nextId(): string {
  _toastCounter += 1;
  return `t${Date.now().toString(36)}-${_toastCounter}`;
}

const DEFAULT_DURATION = 4_000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Keep timeout handles outside React state — we only need them to clean up.
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    ({ message, variant = "info", durationMs = DEFAULT_DURATION }: PushArgs): string => {
      const id = nextId();
      const toast: Toast = { id, message, variant, durationMs };
      setToasts((prev) => [...prev, toast]);
      if (durationMs > 0) {
        const handle = setTimeout(() => {
          // setTimeout fires once — call dismiss directly (it cleans up the map).
          setToasts((prev) => prev.filter((t) => t.id !== id));
          timers.current.delete(id);
        }, durationMs);
        timers.current.set(id, handle);
      }
      return id;
    },
    [],
  );

  // Drain any remaining timers on unmount.
  useEffect(() => {
    const t = timers.current;
    return () => {
      for (const handle of t.values()) clearTimeout(handle);
      t.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, push, dismiss }),
    [toasts, push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): {
  push: ToastContextValue["push"];
  dismiss: ToastContextValue["dismiss"];
} {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Not fatal — tests render components in isolation. We return a no-op
    // pair so component code can call push() without a guard.
    return {
      push: () => "",
      dismiss: () => undefined,
    };
  }
  return { push: ctx.push, dismiss: ctx.dismiss };
}

/** Read the full toast list — used by tests and the viewport. */
export function useToasts(): Toast[] {
  const ctx = useContext(ToastContext);
  return ctx?.toasts ?? [];
}

function variantClasses(v: ToastVariant): string {
  switch (v) {
    case "success":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "error":
      return "border-red-500/50 bg-red-500/10 text-red-200";
    case "info":
      return "border-zinc-700 bg-zinc-900/95 text-zinc-100";
  }
}

function ToastViewport({ toasts, dismiss }: { toasts: Toast[]; dismiss(id: string): void }) {
  if (toasts.length === 0) return null;
  return (
    // Fixed, top-right, beneath the safe-area inset on iOS standalone.
    <section
      className="fixed top-2 right-2 z-30 flex flex-col gap-2 pointer-events-none pt-safe"
      aria-label="notifications"
    >
      {toasts.map((t) => (
        <output
          key={t.id}
          aria-live={t.variant === "error" ? "assertive" : "polite"}
          className={`pointer-events-auto min-w-[220px] max-w-[320px] rounded-md border px-3 py-2.5 text-xs shadow-lg backdrop-blur ${variantClasses(t.variant)}`}
        >
          <div className="flex items-start gap-2">
            <span className="flex-1 leading-snug">{t.message}</span>
            <button
              type="button"
              aria-label="dismiss notification"
              onClick={() => dismiss(t.id)}
              className="shrink-0 -mr-1 -mt-0.5 px-1 text-current opacity-70 hover:opacity-100"
            >
              ×
            </button>
          </div>
        </output>
      ))}
    </section>
  );
}
