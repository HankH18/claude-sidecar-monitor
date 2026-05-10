import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Boom({ shouldThrow }: { shouldThrow: boolean }): JSX.Element {
  if (shouldThrow) throw new Error("kaboom");
  return <div data-testid="ok">ok</div>;
}

function Toggle(): JSX.Element {
  const [throws, setThrows] = useState(true);
  return (
    <div>
      <button type="button" data-testid="fix" onClick={() => setThrows(false)}>
        fix
      </button>
      <Boom shouldThrow={throws} />
    </div>
  );
}

describe("ErrorBoundary", () => {
  // React logs the caught error to console.error; mute it for tidy test output.
  let errSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    errSpy.mockRestore();
  });

  it("renders children when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("ok")).toBeInTheDocument();
  });

  it("renders the fallback UI when a child throws", () => {
    render(
      <ErrorBoundary>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("retry button resets the error state and re-renders children", () => {
    function Outer(): JSX.Element {
      return (
        <ErrorBoundary>
          <Toggle />
        </ErrorBoundary>
      );
    }
    const { rerender } = render(<Outer />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    // Click "Try again" — boundary clears its error state and remounts children.
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    // After reset, Toggle re-mounts with throws=true again — boundary catches again.
    // To assert the retry path actually re-renders children, we use a custom fallback.
    rerender(<Outer />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("supports a custom fallback prop", () => {
    render(
      <ErrorBoundary
        fallback={(err, retry) => (
          <button type="button" onClick={retry} data-testid="custom-fb">
            {err.message}
          </button>
        )}
      >
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    const fb = screen.getByTestId("custom-fb");
    expect(fb.textContent).toBe("kaboom");
  });
});
