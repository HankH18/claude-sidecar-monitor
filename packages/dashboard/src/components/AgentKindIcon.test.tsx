import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AgentKindIcon from "./AgentKindIcon";

describe("AgentKindIcon", () => {
  it("renders nothing when kind is null", () => {
    const { container } = render(<AgentKindIcon kind={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a glyph + accessible label for a known kind", () => {
    render(<AgentKindIcon kind="coder" />);
    const el = screen.getByRole("img", { name: /coder/i });
    expect(el.getAttribute("data-kind")).toBe("coder");
    expect(el.getAttribute("data-muted")).toBe("false");
  });

  it("applies muted styling when confidence is below the threshold (< 0.4)", () => {
    render(<AgentKindIcon kind="planner" confidence={0.3} />);
    const el = screen.getByRole("img", { name: /planner \(low confidence\)/i });
    expect(el.getAttribute("data-muted")).toBe("true");
    expect(el.className).toMatch(/opacity-60/);
  });

  it("does not mute at exactly the threshold (0.4 is not <)", () => {
    render(<AgentKindIcon kind="planner" confidence={0.4} />);
    const el = screen.getByRole("img");
    expect(el.getAttribute("data-muted")).toBe("false");
  });

  it("renders the label when showLabel is true", () => {
    render(<AgentKindIcon kind="debugger" showLabel />);
    expect(screen.getByText("debugger")).toBeInTheDocument();
  });
});
