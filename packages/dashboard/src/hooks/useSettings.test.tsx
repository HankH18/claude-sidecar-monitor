import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMockSettings } from "../api/mock";
import { setUseMockOverride } from "../api/mode";
import { useSettings } from "./useSettings";

describe("useSettings (mock mode)", () => {
  beforeEach(() => setUseMockOverride(true));
  afterEach(() => setUseMockOverride(null));

  it("loads from the in-memory mock", async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.settings).not.toBeNull();
    expect(result.current.settings?.hang_yellow_ms).toBe(60_000);
  });

  it("save() updates the in-memory mock settings", async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.save({ ntfy_topic: "csm-from-test" });
    });
    expect(getMockSettings().ntfy_topic).toBe("csm-from-test");
    expect(result.current.settings?.ntfy_topic).toBe("csm-from-test");
  });
});

describe("useSettings (live mode)", () => {
  beforeEach(() => setUseMockOverride(false));
  afterEach(() => {
    setUseMockOverride(null);
    vi.restoreAllMocks();
  });

  it("GETs /api/settings on mount and PATCHes on save", async () => {
    const responses: Record<string, unknown> = {
      "GET /api/settings": {
        hang_yellow_ms: 30_000,
        hang_red_ms: 90_000,
        ntfy_topic: "live-topic",
      },
      "PATCH /api/settings": {
        hang_yellow_ms: 30_000,
        hang_red_ms: 90_000,
        ntfy_topic: "patched",
      },
    };
    const fetchSpy = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = responses[`${method} ${url}`];
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchSpy);

    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/settings",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(result.current.settings?.ntfy_topic).toBe("live-topic");

    await act(async () => {
      await result.current.save({ ntfy_topic: "patched" });
    });
    const patchCall = fetchSpy.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patchCall).toBeDefined();
    expect(patchCall?.[0]).toBe("/api/settings");
    expect(JSON.parse((patchCall?.[1] as RequestInit).body as string)).toEqual({
      ntfy_topic: "patched",
    });
    expect(result.current.settings?.ntfy_topic).toBe("patched");
  });
});
