import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionRequest } from "../api/types";
import PermissionSheet from "./PermissionSheet";

function fakeRequest(overrides: Partial<PermissionRequest> = {}): PermissionRequest {
  return {
    id: 42,
    session_id: "sess-deadbeef",
    tool_use_id: "tu-1",
    tool_name: "Bash",
    tool_input: { command: "rm -rf node_modules" },
    status: "pending",
    decision_reason: null,
    requested_at: new Date().toISOString(),
    decided_at: null,
    ...overrides,
  };
}

describe("PermissionSheet", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the tool name, session link, and pretty-printed input", () => {
    render(
      <MemoryRouter>
        <PermissionSheet request={fakeRequest()} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /Bash/i })).toBeInTheDocument();
    // Session link uses a 12-char prefix (then an ellipsis glyph).
    expect(screen.getByText(/session sess-deadbee/i)).toBeInTheDocument();
    expect(screen.getByText(/rm -rf node_modules/)).toBeInTheDocument();
  });

  it("POSTs the decision and calls onClose on success", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify(fakeRequest({ status: "allow", decided_at: new Date().toISOString() })),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const onClose = vi.fn();
    const onDecided = vi.fn();
    render(
      <MemoryRouter>
        <PermissionSheet request={fakeRequest()} onClose={onClose} onDecided={onDecided} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Allow$/ }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onDecided).toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/permission-requests/42/decide",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders an expired message on 409 (already_decided)", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ detail: { error: { code: "already_decided", message: "gone" } } }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    render(
      <MemoryRouter>
        <PermissionSheet request={fakeRequest()} onClose={() => {}} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Allow$/ }));
    await waitFor(() => {
      expect(screen.getByText(/Already decided/i)).toBeInTheDocument();
    });
  });
});
