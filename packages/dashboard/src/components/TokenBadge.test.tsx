import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TokenBadge, { formatTokens } from "./TokenBadge";

describe("formatTokens", () => {
  it("formats sub-thousand counts as bare numbers", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(999)).toBe("999");
  });
  it("formats thousands with one decimal under 10K", () => {
    expect(formatTokens(1_234)).toBe("1.2K");
    expect(formatTokens(9_900)).toBe("9.9K");
  });
  it("formats thousands without decimals at 10K+", () => {
    expect(formatTokens(12_345)).toBe("12K");
    expect(formatTokens(123_456)).toBe("123K");
  });
  it("formats millions", () => {
    expect(formatTokens(1_500_000)).toBe("1.50M");
    expect(formatTokens(15_000_000)).toBe("15M");
  });
});

describe("TokenBadge", () => {
  it("shows input/output as the primary line", () => {
    render(<TokenBadge input={12_300} output={4_500} />);
    const wrap = screen.getByLabelText(/tokens:/i);
    expect(wrap.textContent).toContain("12K");
    expect(wrap.textContent).toContain("4.5K");
  });

  it("shows the cache line when cache_read > 0", () => {
    render(<TokenBadge input={1_000} output={500} cacheRead={88_000} cacheWrite={2_000} />);
    const wrap = screen.getByLabelText(/tokens:/i);
    expect(wrap.textContent).toContain("cr");
    expect(wrap.textContent).toContain("88K");
    expect(wrap.textContent).toContain("cw");
  });

  it("hides the cache line when cache values are zero", () => {
    render(<TokenBadge input={100} output={50} />);
    const wrap = screen.getByLabelText(/tokens:/i);
    expect(wrap.textContent).not.toContain("cr ");
  });
});
