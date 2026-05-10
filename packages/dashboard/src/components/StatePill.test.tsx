import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatePill from "./StatePill";

describe("StatePill", () => {
  it("renders the running state with icon and label", () => {
    render(<StatePill state="running" />);
    const el = screen.getByLabelText(/session state: running/i);
    expect(el).toBeInTheDocument();
    expect(el.textContent).toContain("●");
    expect(el.textContent?.toLowerCase()).toContain("running");
  });

  it("supports an override label (e.g. stale)", () => {
    render(<StatePill state="idle" label="stale" />);
    const el = screen.getByLabelText(/session state: stale/i);
    expect(el.textContent?.toLowerCase()).toContain("stale");
  });

  it("renders the hung state with the warn icon and pulse class", () => {
    render(<StatePill state="hung" />);
    const el = screen.getByLabelText(/session state: hung/i);
    expect(el.textContent).toContain("⚠");
    expect(el.className).toMatch(/animate-pulse/);
  });

  it("renders waiting_user with the bell icon", () => {
    render(<StatePill state="waiting_user" />);
    const el = screen.getByLabelText(/session state: waiting/i);
    expect(el.textContent).toContain("🔔");
  });

  it("renders done with the check icon", () => {
    render(<StatePill state="done" />);
    const el = screen.getByLabelText(/session state: done/i);
    expect(el.textContent).toContain("✓");
  });
});
