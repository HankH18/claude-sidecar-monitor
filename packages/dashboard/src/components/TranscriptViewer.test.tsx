import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TranscriptViewer, { type TranscriptViewerMessage } from "./TranscriptViewer";

const NOW = new Date().toISOString();

function makeMessages(): TranscriptViewerMessage[] {
  return [
    {
      message_id: 1,
      role: "user",
      timestamp: NOW,
      content_json: "Please summarise the repo",
    },
    {
      message_id: 2,
      role: "assistant",
      timestamp: NOW,
      content_json: JSON.stringify({
        type: "assistant",
        message: {
          role: "assistant",
          model: "claude-opus-4-7",
          usage: { input_tokens: 800, output_tokens: 200, cache_read_input_tokens: 3200 },
          content: [
            {
              type: "text",
              text: "I'll start by listing the directory.\n\n```ts\nconsole.log('x')\n```",
            },
            { type: "tool_use", id: "tu_1", name: "Bash", input: { command: "ls -la" } },
          ],
        },
      }),
      input_tokens: 800,
      output_tokens: 200,
      cache_read_input_tokens: 3200,
      model: "claude-opus-4-7",
    },
    {
      message_id: 3,
      role: "tool_result",
      timestamp: NOW,
      content_json: JSON.stringify({
        type: "user",
        message: {
          role: "user",
          content: [{ type: "tool_result", tool_use_id: "tu_1", content: "drwxr-xr-x  src" }],
        },
      }),
    },
    {
      message_id: 4,
      role: "assistant",
      timestamp: NOW,
      content_json: JSON.stringify({
        type: "assistant",
        message: {
          role: "assistant",
          content: [
            { type: "thinking", thinking: "Hmm, let me consider the structure." },
            { type: "text", text: "Looks good." },
          ],
        },
      }),
    },
    {
      message_id: 5,
      role: "assistant",
      timestamp: NOW,
      content_json: JSON.stringify({
        type: "assistant",
        message: {
          role: "assistant",
          content: [
            {
              type: "tool_use",
              id: "tu_edit",
              name: "Edit",
              input: {
                file_path: "/repo/file.ts",
                old_string: "const a = 1;",
                new_string: "const a = 2;",
              },
            },
          ],
        },
      }),
    },
  ];
}

describe("TranscriptViewer", () => {
  it("renders one article per message", () => {
    render(<TranscriptViewer messages={makeMessages()} />);
    const articles = screen.getAllByTestId("transcript-message");
    expect(articles).toHaveLength(5);
  });

  it("tags articles by role for selector-driven styling", () => {
    render(<TranscriptViewer messages={makeMessages()} />);
    const articles = screen.getAllByTestId("transcript-message");
    const roles = articles.map((a) => a.dataset.role);
    expect(roles).toContain("user");
    expect(roles).toContain("assistant");
    expect(roles).toContain("tool_result");
  });

  it("renders a tool_use chip with the tool name and one-line summary", () => {
    render(<TranscriptViewer messages={makeMessages()} />);
    expect(screen.getByText("Bash")).toBeInTheDocument();
    expect(screen.getByText("ls -la")).toBeInTheDocument();
  });

  it("renders code fences inside <pre> on the dark code surface", () => {
    const { container } = render(<TranscriptViewer messages={makeMessages()} />);
    const pre = container.querySelector("pre.bg-code-bg");
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain("console.log('x')");
  });

  it("renders the per-turn token attribution on assistant messages", () => {
    render(<TranscriptViewer messages={makeMessages()} />);
    // 800 + 200 = 1000 → "1.0K tokens"; cache_read 3.2K → "3.2K cached".
    const articles = screen.getAllByTestId("transcript-message");
    const assistant = articles.find((a) => a.dataset.role === "assistant");
    expect(assistant?.textContent ?? "").toMatch(/1\.0K tokens/);
    expect(assistant?.textContent ?? "").toMatch(/3\.2K cached/);
  });

  it("collapses tool_result messages behind a show affordance", () => {
    render(<TranscriptViewer messages={makeMessages()} />);
    const articles = screen.getAllByTestId("transcript-message");
    const toolResult = articles.find((a) => a.dataset.role === "tool_result");
    expect(toolResult?.querySelector("details")).not.toBeNull();
  });

  it("renders thinking blocks as a collapsed <details>", () => {
    const { container } = render(<TranscriptViewer messages={makeMessages()} />);
    const detailsWithThought = Array.from(container.querySelectorAll("details summary")).find((s) =>
      s.textContent?.includes("thought"),
    );
    expect(detailsWithThought).toBeTruthy();
  });

  it("renders an Edit tool_use as a chip whose body contains a diff", () => {
    const { container } = render(<TranscriptViewer messages={makeMessages()} />);
    // The synthesised diff prefixes file paths with --- / +++.
    expect(container.textContent).toContain("--- /repo/file.ts");
    expect(container.textContent).toContain("+++ /repo/file.ts");
  });
});
