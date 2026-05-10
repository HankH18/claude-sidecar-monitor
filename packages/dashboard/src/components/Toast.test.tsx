import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast, useToasts } from "./Toast";

/**
 * The hooks live inside the provider — wrap them in a tiny consumer that
 * exposes the imperative API to the test as DOM affordances.
 */
function Harness() {
  const { push, dismiss } = useToast();
  const toasts = useToasts();
  return (
    <div>
      <button type="button" onClick={() => push({ message: "Saved", variant: "success" })}>
        push success
      </button>
      <button
        type="button"
        onClick={() => push({ message: "Boom", variant: "error", durationMs: 0 })}
      >
        push sticky
      </button>
      {toasts[0] ? (
        <button type="button" onClick={() => dismiss(toasts[0].id)}>
          dismiss first
        </button>
      ) : null}
      <span data-testid="count">{toasts.length}</span>
    </div>
  );
}

describe("ToastProvider / useToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("push() adds a toast that auto-dismisses after its duration", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    expect(screen.getByTestId("count").textContent).toBe("0");
    fireEvent.click(screen.getByText("push success"));
    expect(screen.getByTestId("count").textContent).toBe("1");
    expect(screen.getByText("Saved")).toBeInTheDocument();

    // Default duration is 4s — fast-forward past it.
    act(() => {
      vi.advanceTimersByTime(4_000);
    });
    expect(screen.getByTestId("count").textContent).toBe("0");
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("durationMs=0 keeps the toast on screen until dismissed", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("push sticky"));
    expect(screen.getByText("Boom")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    // Still visible — sticky toasts are an explicit opt-in.
    expect(screen.getByText("Boom")).toBeInTheDocument();
    fireEvent.click(screen.getByText("dismiss first"));
    expect(screen.queryByText("Boom")).toBeNull();
  });

  it("renders the dismiss button on each toast and removes on click", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("push success"));
    expect(screen.getByText("Saved")).toBeInTheDocument();
    // The viewport renders an "× dismiss notification" affordance.
    fireEvent.click(screen.getByLabelText(/dismiss notification/i));
    expect(screen.queryByText("Saved")).toBeNull();
  });
});
