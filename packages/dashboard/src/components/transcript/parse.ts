/**
 * Parse a `transcript_messages.content_json` string into structured blocks
 * the viewer can render.
 *
 * Claude Code transcripts store the full raw line from the JSONL file
 * (`packages/collector/src/csm/jsonl/parser.py`). That object can look like:
 *
 *   { type: "user", message: { role, content: "..." | [...] }, ... }
 *   { type: "assistant", message: { model, usage, content: [...] }, ... }
 *   { type: "system", message: { content: "..." }, ... }
 *   { type: "tool_result", message: { content: [...] | "..." }, tool_use_id, ... }
 *
 * The viewer cares about the *blocks* (text / tool_use / tool_result /
 * thinking) and the message-level metadata (model, usage). Everything else
 * gets discarded.
 *
 * This parser is intentionally defensive — older mock fixtures pass a plain
 * string in `content`, and we degrade to a single text block in that case.
 */

export type TextBlock = { type: "text"; text: string };
export type ThinkingBlock = { type: "thinking"; text: string; tokens?: number };
export type ToolUseBlock = {
  type: "tool_use";
  id?: string;
  name: string;
  input: Record<string, unknown>;
};
export type ToolResultBlock = {
  type: "tool_result";
  tool_use_id?: string;
  content: string;
  is_error?: boolean;
};
export type UnknownBlock = { type: "unknown"; raw: unknown };

export type ContentBlock =
  | TextBlock
  | ThinkingBlock
  | ToolUseBlock
  | ToolResultBlock
  | UnknownBlock;

export interface ParsedTranscriptMessage {
  /** "user" | "assistant" | "system" | "tool_result" etc. */
  role: string;
  /** Best-effort assistant model attribution. */
  model?: string;
  /** Per-turn usage from `message.usage`, if present. */
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  };
  blocks: ContentBlock[];
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function blockFromObject(o: Record<string, unknown>): ContentBlock {
  const type = o.type;
  if (type === "text" && typeof o.text === "string") {
    return { type: "text", text: o.text };
  }
  if (type === "thinking") {
    const text =
      typeof o.thinking === "string" ? o.thinking : typeof o.text === "string" ? o.text : "";
    return { type: "thinking", text };
  }
  if (type === "tool_use" && typeof o.name === "string") {
    const id = typeof o.id === "string" ? o.id : undefined;
    const input = asRecord(o.input) ?? {};
    return { type: "tool_use", id, name: o.name, input };
  }
  if (type === "tool_result") {
    const tool_use_id = typeof o.tool_use_id === "string" ? o.tool_use_id : undefined;
    const isErr = o.is_error === true;
    const c = o.content;
    let body: string;
    if (typeof c === "string") {
      body = c;
    } else if (Array.isArray(c)) {
      // tool_result.content is often an array of {type:"text", text} blocks.
      body = c
        .map((b) => {
          const r = asRecord(b);
          if (!r) return typeof b === "string" ? b : "";
          if (typeof r.text === "string") return r.text;
          return JSON.stringify(r);
        })
        .filter(Boolean)
        .join("\n");
    } else {
      body = c === undefined ? "" : JSON.stringify(c);
    }
    return { type: "tool_result", tool_use_id, content: body, is_error: isErr };
  }
  // Fallback: surface anything text-shaped, otherwise tag as unknown.
  if (typeof o.text === "string") return { type: "text", text: o.text };
  return { type: "unknown", raw: o };
}

/**
 * Normalise an arbitrary `message.content` value into a list of blocks.
 *
 *   "hello world"                       → [{text:"hello world"}]
 *   [{type:"text", text:"hi"}]          → [{text:"hi"}]
 *   [{type:"tool_use",...}, ...]        → [{tool_use:...}, ...]
 *   null / undefined                    → []
 */
function blocksFromContent(content: unknown): ContentBlock[] {
  if (content === null || content === undefined) return [];
  if (typeof content === "string") {
    return content === "" ? [] : [{ type: "text", text: content }];
  }
  if (Array.isArray(content)) {
    const out: ContentBlock[] = [];
    for (const item of content) {
      if (typeof item === "string") {
        if (item) out.push({ type: "text", text: item });
        continue;
      }
      const r = asRecord(item);
      if (r) out.push(blockFromObject(r));
    }
    return out;
  }
  // Some shapes hand back an object that's itself a single block.
  const r = asRecord(content);
  if (r) return [blockFromObject(r)];
  return [];
}

/**
 * Parse one transcript row's `content_json` string. Returns a structured
 * representation suitable for the new TranscriptViewer.
 *
 * If the input isn't valid JSON, we still return a parsed object — with
 * a single text block carrying the raw string — so the viewer always has
 * SOMETHING to render. Callers can detect this via `blocks.length === 1
 * && blocks[0].type === "text"`.
 */
export function parseTranscriptContent(
  contentJson: string,
  fallbackRole?: string,
): ParsedTranscriptMessage {
  // Defensive default in case parsing throws or yields a non-object.
  const fallback: ParsedTranscriptMessage = {
    role: fallbackRole ?? "unknown",
    blocks: contentJson ? [{ type: "text", text: contentJson }] : [],
  };

  let parsed: unknown;
  try {
    parsed = JSON.parse(contentJson);
  } catch {
    return fallback;
  }

  // The raw line is *usually* a JSONL row from `~/.claude/projects/.../*.jsonl`
  // — an object with a `message` field. But some older code paths and the
  // mock fixtures stash a plain string here too.
  if (typeof parsed === "string") {
    return { role: fallbackRole ?? "unknown", blocks: [{ type: "text", text: parsed }] };
  }

  if (Array.isArray(parsed)) {
    // Already a block array — treat content as the array.
    return { role: fallbackRole ?? "unknown", blocks: blocksFromContent(parsed) };
  }

  const obj = asRecord(parsed);
  if (!obj) return fallback;

  // Prefer the inner message envelope when present (the real JSONL shape).
  const inner = asRecord(obj.message);
  const role =
    (typeof obj.type === "string" && obj.type) ||
    (inner && typeof inner.role === "string" && inner.role) ||
    fallbackRole ||
    "unknown";

  const model = inner && typeof inner.model === "string" ? inner.model : undefined;
  const usageObj = inner ? asRecord(inner.usage) : null;
  const usage = usageObj
    ? {
        input_tokens: typeof usageObj.input_tokens === "number" ? usageObj.input_tokens : undefined,
        output_tokens:
          typeof usageObj.output_tokens === "number" ? usageObj.output_tokens : undefined,
        cache_read_input_tokens:
          typeof usageObj.cache_read_input_tokens === "number"
            ? usageObj.cache_read_input_tokens
            : undefined,
        cache_creation_input_tokens:
          typeof usageObj.cache_creation_input_tokens === "number"
            ? usageObj.cache_creation_input_tokens
            : undefined,
      }
    : undefined;

  // Locate the content payload. Several layouts in the wild:
  //   { message: { content: ... } }                — most common
  //   { content: ... }                              — older / hand-rolled
  //   { type: "tool_result", content: ... }         — collapsed tool result row
  let contentSrc: unknown;
  if (inner && "content" in inner) {
    contentSrc = inner.content;
  } else if ("content" in obj) {
    contentSrc = obj.content;
  }

  let blocks = blocksFromContent(contentSrc);

  // Last-resort fallback so an unparseable shape still shows the raw JSON
  // text instead of an empty block.
  if (blocks.length === 0) {
    blocks = [{ type: "text", text: contentJson }];
  }

  return { role, model, usage, blocks };
}

/**
 * Compact one-line input summary for a tool_use block.
 *
 * Examples:
 *   Bash: ls -la /tmp
 *   Edit: packages/dashboard/src/App.tsx
 *   Read: README.md
 *   Agent: explore the routing layer
 *   Grep: pattern "TODO" in src/
 *
 * Truncates to ~`max` chars so the chip stays a single line.
 */
export function summarizeToolInput(name: string, input: Record<string, unknown>, max = 60): string {
  const get = (k: string): string | undefined => {
    const v = input[k];
    return typeof v === "string" ? v : undefined;
  };
  let preview: string;
  switch (name) {
    case "Bash":
      preview = get("command") ?? "";
      break;
    case "Edit":
    case "MultiEdit":
    case "Write":
    case "Read":
    case "NotebookEdit":
      preview = get("file_path") ?? get("path") ?? "";
      break;
    case "Glob":
      preview = get("pattern") ?? "";
      break;
    case "Grep":
      preview = get("pattern") ?? "";
      break;
    case "Task":
    case "Agent": {
      preview = get("description") ?? get("prompt") ?? "";
      break;
    }
    case "WebFetch":
    case "WebSearch":
      preview = get("url") ?? get("query") ?? "";
      break;
    default: {
      // Pick the longest string field as a heuristic.
      const candidates = Object.values(input).filter((v) => typeof v === "string") as string[];
      candidates.sort((a, b) => b.length - a.length);
      preview = candidates[0] ?? JSON.stringify(input);
    }
  }
  preview = preview.replace(/\s+/g, " ").trim();
  if (preview.length > max) preview = `${preview.slice(0, max - 1)}…`;
  return preview;
}
