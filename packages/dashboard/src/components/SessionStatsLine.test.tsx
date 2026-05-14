import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SessionStatsLine from "./SessionStatsLine";

const NOW_ISO = new Date().toISOString();
const FIVE_MIN_AGO = new Date(Date.now() - 5 * 60_000).toISOString();
const TWO_HOURS_AGO = new Date(Date.now() - 2 * 60 * 60_000).toISOString();

describe("SessionStatsLine", () => {
  it("renders the stats line container with tabular nums", () => {
    render(<SessionStatsLine startedAt={FIVE_MIN_AGO} lastEventAt={NOW_ISO} live />);
    const el = screen.getByTestId("session-stats-line");
    expect(el).toBeInTheDocument();
    expect(el.className).toContain("tabular-nums");
  });

  it("shows a non-zero duration for a 5-min-old session", () => {
    render(<SessionStatsLine startedAt={FIVE_MIN_AGO} live />);
    const text = screen.getByTestId("session-stats-line").textContent ?? "";
    expect(text).toMatch(/5m|4m|6m/);
  });

  it("renders an em-dash when tokensLastHour is null", () => {
    render(<SessionStatsLine startedAt={FIVE_MIN_AGO} tokensLastHour={null} />);
    expect(screen.getByTestId("session-stats-line").textContent).toContain("—");
  });

  it("renders the trailing-60-min tokens with /h suffix when > 0", () => {
    render(<SessionStatsLine startedAt={FIVE_MIN_AGO} tokensLastHour={1_400} />);
    expect(screen.getByTestId("session-stats-line").textContent).toContain("1.4K/h");
  });

  it("renders the total tokens cell when totalTokens is set", () => {
    render(
      <SessionStatsLine startedAt={FIVE_MIN_AGO} totalTokens={12_400} tokensLastHour={null} />,
    );
    expect(screen.getByTestId("session-stats-line").textContent).toContain("12K");
  });

  it("hides token columns when hideTokens=true (virtual subagent rows)", () => {
    render(
      <SessionStatsLine
        startedAt={FIVE_MIN_AGO}
        totalTokens={12_400}
        tokensLastHour={500}
        hideTokens
      />,
    );
    const text = screen.getByTestId("session-stats-line").textContent ?? "";
    expect(text).not.toContain("12K");
    expect(text).not.toContain("/h");
  });

  it("uses completedAt as the duration endpoint when supplied", () => {
    // Started 2h ago, completed 5m ago → ~1h 55m duration.
    render(<SessionStatsLine startedAt={TWO_HOURS_AGO} completedAt={FIVE_MIN_AGO} live={false} />);
    const text = screen.getByTestId("session-stats-line").textContent ?? "";
    expect(text).toMatch(/1h\s5[0-9]m/);
  });
});
