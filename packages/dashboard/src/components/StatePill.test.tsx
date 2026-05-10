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

  it("hung state additionally gets the pulsing ring class (not just the dot)", () => {
    // Round-1 design contract: hung sessions deserve a stronger signal than
    // a fading icon — they get a red box-shadow ring driven by the
    // `animate-pulse-ring` keyframes (defined in theme.css). Verify both the
    // class is applied AND that it's only on hung (running shouldn't have it).
    const { rerender, container } = render(<StatePill state="hung" />);
    const hung = container.firstElementChild as HTMLElement;
    expect(hung.className).toMatch(/animate-pulse-ring/);

    rerender(<StatePill state="running" />);
    const running = container.firstElementChild as HTMLElement;
    expect(running.className).not.toMatch(/animate-pulse-ring/);
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
