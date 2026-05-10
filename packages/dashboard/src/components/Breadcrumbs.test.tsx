import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import Breadcrumbs from "./Breadcrumbs";

describe("Breadcrumbs", () => {
  it("renders intermediate crumbs as links and the last as plain text", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          items={[
            { label: "Live", to: "/" },
            { label: "sidecar", to: "/projects/abc" },
            { label: "alpha" },
          ]}
        />
      </MemoryRouter>,
    );

    // First crumb = link to /
    const live = screen.getByRole("link", { name: "Live" });
    expect(live).toHaveAttribute("href", "/");

    // Middle crumb = link to project
    const project = screen.getByRole("link", { name: "sidecar" });
    expect(project).toHaveAttribute("href", "/projects/abc");

    // Last crumb is NOT a link — it's the current page.
    expect(screen.queryByRole("link", { name: "alpha" })).toBeNull();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });

  it("renders nothing for an empty items array", () => {
    const { container } = render(
      <MemoryRouter>
        <Breadcrumbs items={[]} />
      </MemoryRouter>,
    );
    expect(container.querySelector("nav")).toBeNull();
  });

  it("uses aria-current=page on the last crumb for accessibility", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: "Live", to: "/" }, { label: "alpha" }]} />
      </MemoryRouter>,
    );
    const current = screen.getByText("alpha");
    expect(current).toHaveAttribute("aria-current", "page");
  });
});
