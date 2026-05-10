import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getMockSettings } from "../api/mock";
import { setUseMockOverride } from "../api/mode";
import Settings from "./Settings";

describe("Settings", () => {
  beforeEach(() => {
    setUseMockOverride(true);
  });
  afterEach(() => {
    setUseMockOverride(null);
  });

  it("populates the form from mock settings", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    const yellow = await screen.findByLabelText(/hang yellow threshold/i);
    const red = screen.getByLabelText(/hang red threshold/i);
    const ntfy = screen.getByLabelText(/ntfy.sh topic/i);
    expect((yellow as HTMLInputElement).value).toBe("60000");
    expect((red as HTMLInputElement).value).toBe("180000");
    expect((ntfy as HTMLInputElement).value).toBeTruthy();
  });

  it("does NOT render plan_seat_type", () => {
    const { container } = render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    expect(container.textContent ?? "").not.toMatch(/plan_seat_type/i);
  });

  it("save patches the in-memory mock settings", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    const ntfy = (await screen.findByLabelText(/ntfy.sh topic/i)) as HTMLInputElement;
    fireEvent.change(ntfy, { target: { value: "csm-test-topic" } });
    fireEvent.submit(screen.getByRole("button", { name: /save/i }).closest("form")!);
    await waitFor(() => {
      expect(getMockSettings().ntfy_topic).toBe("csm-test-topic");
    });
  });

  it("opens the change-passphrase modal when its button is clicked", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /change passphrase/i }));
    expect(screen.getByLabelText("old passphrase")).toBeInTheDocument();
    expect(screen.getByLabelText("new passphrase")).toBeInTheDocument();
    expect(screen.getByLabelText("confirm new passphrase")).toBeInTheDocument();
  });
});
