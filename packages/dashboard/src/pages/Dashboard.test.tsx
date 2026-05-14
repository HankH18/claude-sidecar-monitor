import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setUseMockOverride } from "../api/mode";
import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("renders the page heading", async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /^dashboard$/i })).toBeInTheDocument();
  });

  it("renders all four KPI tiles by label", async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    // "Live agents" appears in BOTH the StatTile label and the drill-down
    // link below — assert getAllByText finds at least one of each.
    expect((await screen.findAllByText(/live agents/i)).length).toBeGreaterThanOrEqual(1);
    // "hung" appears in BOTH the StatTile and the state breakdown row,
    // so allow >= 1 match.
    expect(screen.getAllByText(/^hung$/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/tokens today/i)).toBeInTheDocument();
    expect(screen.getByText(/this hour/i)).toBeInTheDocument();
  });

  it("renders the events-per-minute sparkline section", async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    // Mock mode returns an empty buckets array → the sparkline shows
    // "No events recorded yet." instead of the bars.
    expect(await screen.findByText(/events ?\/ ?minute/i)).toBeInTheDocument();
    expect(screen.getByText(/no events recorded yet/i)).toBeInTheDocument();
  });

  it("renders the state breakdown and top-models windows", async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/live by state/i)).toBeInTheDocument();
    expect(screen.getByText(/top models/i)).toBeInTheDocument();
  });

  it("renders drill-down links to /live, /tokens, /settings", async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    // The "→" suffix is unique to the drill-down row at the bottom; the
    // StatTile labels don't carry an arrow.
    expect(await screen.findByRole("link", { name: /live agents →/i })).toHaveAttribute(
      "href",
      "/live",
    );
    expect(screen.getByRole("link", { name: /token breakdown →/i })).toHaveAttribute(
      "href",
      "/tokens",
    );
    expect(screen.getByRole("link", { name: /settings →/i })).toHaveAttribute("href", "/settings");
  });
});
