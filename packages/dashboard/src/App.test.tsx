import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
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
