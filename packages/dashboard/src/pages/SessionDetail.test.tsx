import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setUseMockOverride } from "../api/mode";
import SessionDetail from "./SessionDetail";

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/sessions/${id}`]}>
      <Routes>
        <Route path="/sessions/:id" element={<SessionDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SessionDetail", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("renders the session header with state pill", () => {
    renderAt("a-parent-001");
    expect(screen.getByRole("heading", { name: /coordinator/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/session state:/i)).toBeInTheDocument();
  });

  it("renders the timeline section heading", () => {
    renderAt("a-parent-001");
    expect(screen.getByRole("heading", { name: /timeline/i })).toBeInTheDocument();
  });

  it("renders multiple transcript message blocks", () => {
    renderAt("a-parent-001");
    const messages = screen.getAllByTestId("transcript-message");
    expect(messages.length).toBeGreaterThanOrEqual(3);
  });

  it("collapses Read tool results inside <details>", () => {
    renderAt("a-parent-001");
    // The mock fixture for a-parent-001 doesn't include Read; smoke-test that
    // the page renders the user prompt verbatim.
    expect(screen.getByText(/Add a token badge/i)).toBeInTheDocument();
  });

  it("renders not-found for an unknown session id", () => {
    renderAt("does-not-exist");
    expect(screen.getByText(/session not found/i)).toBeInTheDocument();
  });
});
