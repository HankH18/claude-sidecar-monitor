import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ConfirmDialog from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders title + description and the confirm/cancel buttons", () => {
    render(
      <ConfirmDialog
        open
        title="Purge old data?"
        description="Deletes 42 rows older than 2026-01-01."
        confirmLabel="Purge"
        intent="danger"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByText(/purge old data/i)).toBeInTheDocument();
    expect(screen.getByText(/Deletes 42 rows/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /purge/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("calls onCancel when the cancel button is clicked", () => {
    const cancel = vi.fn();
    render(
      <ConfirmDialog open title="Are you sure?" onConfirm={() => undefined} onCancel={cancel} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("calls onConfirm when the primary button is clicked", () => {
    const confirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Are you sure?"
        confirmLabel="Yes"
        onConfirm={confirm}
        onCancel={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /yes/i }));
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("returns null when open=false (no dialog in DOM)", () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="Hidden"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(container.querySelector("dialog")).toBeNull();
  });
});
