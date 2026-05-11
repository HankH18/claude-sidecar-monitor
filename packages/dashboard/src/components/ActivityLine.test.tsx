import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ActivityLine from "./ActivityLine";

describe("ActivityLine", () => {
  it("renders an em-dash when summary is null", () => {
    render(<ActivityLine summary={null} updatedAt={null} />);
    expect(screen.getByTestId("activity-line").textContent).toContain("—");
  });

  it("renders the summary and a relative timestamp", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    render(<ActivityLine summary="editing src/foo.ts" updatedAt={iso} />);
    const el = screen.getByTestId("activity-line");
    expect(el.textContent).toContain("editing src/foo.ts");
    // Anywhere between "just now" and "30s ago" depending on timing.
    expect(el.textContent).toMatch(/(just now|\d+s ago)/);
  });
});
