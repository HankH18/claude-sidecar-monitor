import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setUseMockOverride } from "../api/mode";
import Settings from "./Settings";

/**
 * Round-1 design contract: every interactive element gets a visible
 * focus ring (not just a hover affordance). The implementation lives in
 * `theme.css` as a `:focus-visible` rule on a :where() selector list, so we
 * verify two things:
 *   (1) the CSS rule itself ships in theme.css (the artifact under review),
 *   (2) the page actually renders a primary button that the rule will hit.
 *
 * jsdom doesn't apply external stylesheets to computed styles, so a CSS
 * source-presence assertion is the most stable way to lock the contract in.
 */
describe("focus ring on primary action", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("primary Save button is focusable from the keyboard", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    const save = (await screen.findByRole("button", { name: /^save$/i })) as HTMLButtonElement;
    // Ensure the element exists and isn't disabled by default.
    expect(save).toBeInTheDocument();
    expect(save).not.toBeDisabled();
    // Programmatically focus the button — focus-visible would apply on real
    // keyboard navigation; here we just confirm it can hold focus.
    save.focus();
    expect(document.activeElement).toBe(save);
  });

  it("theme.css declares a :focus-visible outline on interactive elements", () => {
    const themeCss = readFileSync(join(process.cwd(), "src/theme.css"), "utf8");
    expect(themeCss).toMatch(/:focus-visible/);
    expect(themeCss).toMatch(/outline:\s*2px\s+solid/);
    // The selector list should cover at least button + a + input so all of
    // the page's primary CTAs receive the ring.
    expect(themeCss).toMatch(/button/);
    expect(themeCss).toMatch(/\ba\b/);
    expect(themeCss).toMatch(/input/);
  });
});
