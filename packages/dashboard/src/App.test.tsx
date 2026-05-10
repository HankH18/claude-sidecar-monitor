import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "./App";
import { setUseMockOverride } from "./api/mode";

describe("App", () => {
  beforeEach(() => {
    // The header now mounts a stream subscriber via ConnectionStatus, so we
    // run App tests in mock mode to avoid touching the real EventSource API
    // (which jsdom doesn't implement).
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("renders the Sidecar header", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Sidecar")).toBeInTheDocument();
  });

  it("renders the Live tab marker", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Live" })).toBeInTheDocument();
  });

  it("renders not-found on unknown route", () => {
    render(
      <MemoryRouter initialEntries={["/nope"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Page not found/i)).toBeInTheDocument();
  });
});
