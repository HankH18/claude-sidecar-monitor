import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setUseMockOverride } from "../api/mode";
import ProjectDetail from "./ProjectDetail";

const PROJECT_A = "/Users/hank/code/sidecar";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:encoded" element={<ProjectDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectDetail", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("renders the project label and summary card", () => {
    renderAt(`/projects/${encodeURIComponent(PROJECT_A)}`);
    expect(screen.getByRole("heading", { name: /sidecar/i })).toBeInTheDocument();
    // Summary fields.
    expect(screen.getByText(/agents/i)).toBeInTheDocument();
    expect(screen.getByText(/tool calls/i)).toBeInTheDocument();
    expect(screen.getByText(/total tokens/i)).toBeInTheDocument();
  });

  it("renders the parent agent_type and both children in the tree", () => {
    renderAt(`/projects/${encodeURIComponent(PROJECT_A)}`);
    // The mock fixture has parent=coordinator, children=implementor + verifier.
    expect(screen.getAllByText(/coordinator/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/implementor/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/verifier/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders a subtree-rollup label on a parent node with children", () => {
    renderAt(`/projects/${encodeURIComponent(PROJECT_A)}`);
    // Subtree label appears only on parent nodes.
    expect(screen.getAllByText(/subtree/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/self /i).length).toBeGreaterThanOrEqual(1);
  });
});
