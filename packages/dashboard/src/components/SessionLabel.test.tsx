import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Session } from "../api/types";
import SessionLabel from "./SessionLabel";

function baseSession(overrides: Partial<Session>): Session {
  return {
    session_id: "abcd1234-5678-90ef-1234-567890abcdef",
    parent_session_id: null,
    worktree_root: "/tmp/x",
    project_label: null,
    cwd: "/tmp/x",
    agent_type: null,
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

describe("SessionLabel", () => {
  it("prefers the V2 title when present", () => {
    render(
      <SessionLabel
        session={baseSession({
          title: "Refactor TokenBadge",
          nickname: "bright-otter-0421",
          agent_type: "coordinator",
        })}
      />,
    );
    const el = screen.getByTestId("session-label");
    expect(el.textContent).toBe("Refactor TokenBadge");
    expect(el.getAttribute("data-source")).toBe("title");
    // Title tooltip is the full session_id so devs can copy it.
    expect(el.getAttribute("title")).toMatch(/^abcd1234-/);
  });

  it("falls back to nickname when title is empty", () => {
    render(
      <SessionLabel
        session={baseSession({ nickname: "bright-otter-0421", agent_type: "coordinator" })}
      />,
    );
    const el = screen.getByTestId("session-label");
    expect(el.textContent).toBe("bright-otter-0421");
    expect(el.getAttribute("data-source")).toBe("nickname");
  });

  it("falls back to agent_type when title + nickname are empty", () => {
    render(<SessionLabel session={baseSession({ agent_type: "coordinator" })} />);
    const el = screen.getByTestId("session-label");
    expect(el.textContent).toBe("coordinator");
    expect(el.getAttribute("data-source")).toBe("agent_type");
  });

  it("falls back to a shortened session_id as the last resort", () => {
    render(<SessionLabel session={baseSession({})} />);
    const el = screen.getByTestId("session-label");
    // First 8 chars of the seeded id.
    expect(el.textContent).toBe("abcd1234");
    expect(el.getAttribute("data-source")).toBe("session_id");
  });
});
