import { describe, expect, it } from "vitest";
import { parseTranscriptContent, summarizeToolInput } from "./parse";

describe("parseTranscriptContent", () => {
  it("handles a plain string content_json (legacy mock shape)", () => {
    const out = parseTranscriptContent("hello world", "user");
    expect(out.role).toBe("user");
    expect(out.blocks).toHaveLength(1);
    expect(out.blocks[0]).toEqual({ type: "text", text: "hello world" });
  });

  it("returns a single text block when input is not valid JSON", () => {
    const out = parseTranscriptContent("{not json", "assistant");
    expect(out.blocks[0]).toMatchObject({ type: "text" });
  });

  it("parses a JSONL assistant row with text + tool_use blocks", () => {
    const raw = JSON.stringify({
      type: "assistant",
      message: {
        role: "assistant",
        model: "claude-opus-4-7",
        usage: { input_tokens: 100, output_tokens: 25, cache_read_input_tokens: 8 },
        content: [
          { type: "text", text: "Let me run the tests." },
          { type: "tool_use", id: "tu_1", name: "Bash", input: { command: "bun run test" } },
        ],
      },
    });
    const out = parseTranscriptContent(raw);
    expect(out.role).toBe("assistant");
    expect(out.model).toBe("claude-opus-4-7");
    expect(out.usage?.input_tokens).toBe(100);
    expect(out.usage?.cache_read_input_tokens).toBe(8);
    expect(out.blocks).toHaveLength(2);
    expect(out.blocks[0]).toMatchObject({ type: "text", text: "Let me run the tests." });
    expect(out.blocks[1]).toMatchObject({ type: "tool_use", name: "Bash" });
  });

  it("parses tool_result content arrays into a single text body", () => {
    const raw = JSON.stringify({
      type: "user",
      message: {
        role: "user",
        content: [
          {
            type: "tool_result",
            tool_use_id: "tu_1",
            content: [
              { type: "text", text: "ok" },
              { type: "text", text: "next line" },
            ],
          },
        ],
      },
    });
    const out = parseTranscriptContent(raw);
    expect(out.blocks).toHaveLength(1);
    const b = out.blocks[0];
    expect(b.type).toBe("tool_result");
    if (b.type === "tool_result") {
      expect(b.content).toBe("ok\nnext line");
      expect(b.tool_use_id).toBe("tu_1");
    }
  });

  it("flags is_error on tool_result blocks", () => {
    const raw = JSON.stringify({
      type: "user",
      message: {
        role: "user",
        content: [{ type: "tool_result", tool_use_id: "tu_x", content: "boom", is_error: true }],
      },
    });
    const out = parseTranscriptContent(raw);
    const b = out.blocks[0];
    expect(b.type).toBe("tool_result");
    if (b.type === "tool_result") {
      expect(b.is_error).toBe(true);
      expect(b.content).toBe("boom");
    }
  });

  it("parses thinking blocks", () => {
    const raw = JSON.stringify({
      type: "assistant",
      message: {
        role: "assistant",
        content: [{ type: "thinking", thinking: "considering options…" }],
      },
    });
    const out = parseTranscriptContent(raw);
    expect(out.blocks[0]).toEqual({ type: "thinking", text: "considering options…" });
  });

  it("falls back to a single text block when content shape is unrecognised", () => {
    const raw = JSON.stringify({ foo: "bar" });
    const out = parseTranscriptContent(raw, "user");
    expect(out.blocks).toHaveLength(1);
    expect(out.blocks[0].type).toBe("text");
  });

  it("accepts a top-level block array directly", () => {
    const raw = JSON.stringify([
      { type: "text", text: "first" },
      { type: "text", text: "second" },
    ]);
    const out = parseTranscriptContent(raw);
    expect(out.blocks).toHaveLength(2);
    expect(out.blocks[0]).toMatchObject({ text: "first" });
  });
});

describe("summarizeToolInput", () => {
  it("summarises Bash by the command field", () => {
    expect(summarizeToolInput("Bash", { command: "ls -la /tmp" })).toBe("ls -la /tmp");
  });

  it("summarises Edit/Read/Write by file_path", () => {
    expect(summarizeToolInput("Edit", { file_path: "/a/b/c.ts" })).toBe("/a/b/c.ts");
    expect(summarizeToolInput("Read", { file_path: "/a/b/c.ts" })).toBe("/a/b/c.ts");
    expect(summarizeToolInput("Write", { file_path: "/a/b/c.ts" })).toBe("/a/b/c.ts");
  });

  it("summarises Task by description", () => {
    expect(
      summarizeToolInput("Task", {
        description: "explore the routing layer",
        prompt: "long prompt body…",
      }),
    ).toBe("explore the routing layer");
  });

  it("truncates long previews to the max length", () => {
    const long = "a".repeat(120);
    const out = summarizeToolInput("Bash", { command: long }, 60);
    expect(out.length).toBe(60);
    expect(out.endsWith("…")).toBe(true);
  });

  it("falls back to the longest string field for unknown tools", () => {
    const out = summarizeToolInput("MysteryTool", { tiny: "x", body: "the actual important text" });
    expect(out).toBe("the actual important text");
  });
});
