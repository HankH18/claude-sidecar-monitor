import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("renders title, message, and a default illustration", () => {
    render(
      <EmptyState
        title="No agents running"
        message="Start a Claude Code session — the receiver listens at :8765."
      />,
    );
    // status role surfaces the empty state to assistive tech
    const card = screen.getByRole("status");
    expect(card).toBeInTheDocument();
    // title + message render as text
    expect(screen.getByText(/No agents running/i)).toBeInTheDocument();
    expect(screen.getByText(/Start a Claude Code session/i)).toBeInTheDocument();
    // an SVG illustration is present (not just text)
    expect(card.querySelector("svg")).not.toBeNull();
  });

  it("renders a custom illustration node when provided", () => {
    render(
      <EmptyState
        illustration={<span data-testid="custom-art">art</span>}
        title="Nothing yet"
        message="Soon."
      />,
    );
    expect(screen.getByTestId("custom-art")).toBeInTheDocument();
  });

  it("renders an action node (call to action) when supplied", () => {
    render(
      <EmptyState
        title="No transcript yet"
        message="Once the agent emits its first turn, it'll show up here."
        action={
          <button type="button" data-testid="cta">
            Reload
          </button>
        }
      />,
    );
    expect(screen.getByTestId("cta")).toBeInTheDocument();
  });
});
