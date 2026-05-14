import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Optional override of the fallback UI; defaults to a friendly card. */
  fallback?: (err: Error, retry: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Top-level error boundary — wraps <App />.
 *
 * On render error: shows a small fallback card with the error message and a
 * "Try again" button that resets state and re-mounts the children. We log to
 * `console.error` so devtools surface the stack trace; production builds can
 * later wire this to a remote error sink.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the stack to the console; this is the only signal in dev.
    console.error("[ErrorBoundary] caught", error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return (
      <div
        role="alert"
        className="min-h-dvh flex items-center justify-center p-6 bg-canvas text-ink"
      >
        <div className="max-w-md space-y-3 rounded-md border border-bad/40 bg-surface p-4 shadow-[0_1px_2px_rgba(80,60,30,0.08)]">
          <h1 className="text-base font-semibold text-bad">Something went wrong.</h1>
          <p className="text-xs text-ink-muted break-all">{error.message}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={this.reset}
              className="inline-flex items-center justify-center min-h-11 px-4 rounded-md bg-cta text-white text-sm font-medium shadow-[0_1px_0_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.25)] hover:bg-cta-hover active:translate-y-px"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined") window.location.reload();
              }}
              className="inline-flex items-center justify-center min-h-11 px-4 rounded-md border border-line-strong bg-surface text-sm text-ink hover:bg-surface-2 active:translate-y-px"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
