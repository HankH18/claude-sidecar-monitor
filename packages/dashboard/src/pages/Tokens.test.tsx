import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setUseMockOverride } from "../api/mode";
import Tokens from "./Tokens";

describe("Tokens", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("renders the three list section headings", () => {
    render(
      <MemoryRouter>
        <Tokens />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /top sessions/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /top projects/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /by model/i })).toBeInTheDocument();
  });

  it("renders the daily totals chart as an accessible figure with svg", () => {
    render(
      <MemoryRouter>
        <Tokens />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /daily totals/i })).toBeInTheDocument();
    // figure[aria-label="daily tokens stacked bar chart"]
    const fig = screen.getByLabelText(/daily tokens stacked bar chart/i);
    expect(fig).toBeInTheDocument();
    expect(fig.querySelector("svg")).not.toBeNull();
  });

  it("does not display plan-ceiling or projection language", () => {
    const { container } = render(
      <MemoryRouter>
        <Tokens />
      </MemoryRouter>,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/projected/i);
    expect(text).not.toMatch(/plan ceiling/i);
    expect(text).not.toMatch(/estimated/i);
  });
});
