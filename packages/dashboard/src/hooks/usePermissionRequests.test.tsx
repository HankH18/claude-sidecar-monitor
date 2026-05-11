import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUseMockOverride } from "../api/mode";
import { usePermissionRequests } from "./usePermissionRequests";

describe("usePermissionRequests", () => {
  beforeEach(() => setUseMockOverride(false));
  afterEach(() => {
    setUseMockOverride(null);
    vi.restoreAllMocks();
  });

  it("fetches the pending list on mount and exposes it", async () => {
    const fetchSpy = vi.fn(async (url: string) => {
      if (url.startsWith("/api/permission-requests")) {
        return new Response(
          JSON.stringify({
            requests: [
              {
                id: 7,
                session_id: "abc",
                tool_use_id: "tu-1",
                tool_name: "Bash",
                tool_input: { command: "ls" },
                status: "pending",
                decision_reason: null,
                requested_at: new Date().toISOString(),
                decided_at: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("nope", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchSpy);

    const { result } = renderHook(() => usePermissionRequests());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.requests).toHaveLength(1);
    expect(result.current.requests[0].tool_name).toBe("Bash");
  });

  it("swallows 503 (api_secret unset) and surfaces an empty list", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ error: { code: "api_secret_unset", message: "run csm install" } }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const { result } = renderHook(() => usePermissionRequests());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.requests).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});
