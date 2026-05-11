import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUseMockOverride } from "../api/mode";
import type { Session, TreeNode } from "../api/types";
import SubagentDetail from "./SubagentDetail";

function renderAt(virtualId: string) {
  return render(
    <MemoryRouter initialEntries={[`/subagents/${encodeURIComponent(virtualId)}`]}>
      <Routes>
        <Route path="/subagents/:virtualId" element={<SubagentDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

function fakeSession(overrides: Partial<Session>): Session {
  return {
    session_id: "parent-001",
    parent_session_id: null,
    worktree_root: "/tmp/proj-a",
    project_label: "proj-a",
    cwd: "/tmp/proj-a",
    agent_type: "coordinator",
    state: "running",
    last_event_at: new Date().toISOString(),
    last_event_name: null,
    last_tool_name: null,
    started_at: new Date().toISOString(),
    completed_at: null,
    primary_model: null,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    ...overrides,
  };
}

describe("SubagentDetail", () => {
  beforeEach(() => {
    // Force live mode so the component issues real fetches we can stub.
    setUseMockOverride(false);
  });
  afterEach(() => {
    setUseMockOverride(null);
    vi.restoreAllMocks();
  });

  it("renders the virtual node's description and metadata", async () => {
    const parent = fakeSession({});
    const virtual: TreeNode = {
      is_virtual: true,
      virtual_id: "parent-001:tool-use-abc",
      description: "Run the failing pytest and report the traceback",
      session: fakeSession({
        session_id: "parent-001:tool-use-abc",
        agent_type: null,
        title: null,
        nickname: "calm-otter-9999",
        agent_kind: "debugger",
        agent_kind_confidence: 0.9,
        state: "running",
      }),
      children: [],
      subtree_tokens: { input: 0, output: 0, cache_read: 0, cache_write: 0, descendant_count: 0 },
    };
    const parentTree: TreeNode = {
      session: parent,
      children: [virtual],
      subtree_tokens: { input: 0, output: 0, cache_read: 0, cache_write: 0, descendant_count: 1 },
    };

    const fetchSpy = vi.fn(async (url: string) => {
      if (url === "/api/state") {
        return new Response(JSON.stringify({ sessions: [parent], settings: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.startsWith("/api/tree")) {
        return new Response(JSON.stringify([parentTree]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderAt("parent-001:tool-use-abc");

    await waitFor(() => {
      expect(screen.getByTestId("subagent-detail")).toBeInTheDocument();
    });
    expect(screen.getByText(/Run the failing pytest/i)).toBeInTheDocument();
    // Nickname fallback in the page header.
    expect(screen.getByRole("heading")).toHaveTextContent(/calm-otter-9999/);
  });

  it("shows a not-found message when the virtual id is missing from the tree", async () => {
    const parent = fakeSession({});
    const parentTree: TreeNode = {
      session: parent,
      children: [],
      subtree_tokens: { input: 0, output: 0, cache_read: 0, cache_write: 0, descendant_count: 0 },
    };
    const fetchSpy = vi.fn(async (url: string) => {
      if (url === "/api/state") {
        return new Response(JSON.stringify({ sessions: [parent], settings: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.startsWith("/api/tree")) {
        return new Response(JSON.stringify([parentTree]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderAt("parent-001:tool-use-missing");

    await waitFor(() => {
      expect(screen.getByText(/Subagent not found\./i)).toBeInTheDocument();
    });
  });
});
