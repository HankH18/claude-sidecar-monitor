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
        className="min-h-dvh flex items-center justify-center p-6 bg-zinc-950 text-zinc-200"
      >
        <div className="max-w-md space-y-3 rounded-md border border-red-500/40 bg-red-500/5 p-4">
          <h1 className="text-base font-semibold text-red-300">Something went wrong.</h1>
          <p className="text-xs text-zinc-400 break-all">{error.message}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={this.reset}
              className="px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-sm hover:bg-emerald-500/30"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined") window.location.reload();
              }}
              className="px-3 py-1.5 rounded border border-zinc-800 text-sm text-zinc-200 hover:bg-zinc-900"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
