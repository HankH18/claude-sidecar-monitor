import { useMemo } from "react";
import { formatRelative } from "../lib/time";
import DiffViewer from "./DiffViewer";
import { formatTokens } from "./TokenBadge";
import {
  type ContentBlock,
  type ParsedTranscriptMessage,
  type ToolUseBlock,
  parseTranscriptContent,
  summarizeToolInput,
} from "./transcript/parse";

/**
 * Minimal raw shape the viewer accepts. The page-level component is free to
 * normalise either the live API row (`{ message_id, role, timestamp,
 * content_json, model? }`) or a mock fixture into this shape.
 *
 * `content_json` may be:
 *   - the literal `content_json` string from `transcript_messages`
 *   - JSON-encoded Anthropic content blocks
 *   - a plain string (for legacy mock rows) — parse.ts handles all three
 */
export interface TranscriptViewerMessage {
  message_id: number;
  role: string;
  timestamp: string;
  content_json: string;
  model?: string | null;
  /** Per-turn usage straight off the column (preferred over usage parsed
   *  from content_json when both are present). */
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
}

interface Props {
  messages: TranscriptViewerMessage[];
  /** Render each message wrapper as a ref-able element. Used by the
   *  scrubber + j/k navigation on SessionDetail. */
  registerRef?(index: number, el: HTMLElement | null): void;
}

/**
 * V3 — prettified transcript renderer. Replaces the raw-JSON dump with:
 *
 *   - user / assistant / system / tool_result wrappers, each with a subtle
 *     left-border tint so role is scannable
 *   - tool_use blocks rendered as one-line chips (`Bash: ls /tmp`) that
 *     expand to full input JSON
 *   - tool_result blocks rendered as a single chip ("→ result (1.4k)")
 *     that expands inline
 *   - thinking blocks collapsed by default
 *   - code fences in assistant text rendered as dark `<pre>` blocks
 *   - Edit / Write tool calls render with the existing DiffViewer
 *
 * Markdown rendering is intentionally minimal: paragraph + line break +
 * triple-backtick code fences. Anything fancier is a TODO — pulling in a
 * markdown lib violates the "no new dependencies" rule.
 */
export default function TranscriptViewer({ messages, registerRef }: Props) {
  return (
    <div className="space-y-3" data-testid="transcript-list">
      {messages.map((m, i) => (
        <div key={m.message_id} ref={(el) => registerRef?.(i, el)} data-message-id={m.message_id}>
          <Message m={m} />
        </div>
      ))}
    </div>
  );
}

function Message({ m }: { m: TranscriptViewerMessage }) {
  const parsed = useMemo<ParsedTranscriptMessage>(
    () => parseTranscriptContent(m.content_json, m.role),
    [m.content_json, m.role],
  );
  // Prefer the role we already have on the row (server-side normalised);
  // fall back to whatever the parser inferred.
  const role = m.role || parsed.role;

  // Role-driven left border + background tint.
  const wrapperClass = roleWrapperClass(role);

  // Pull usage off the row column first; fall back to parsed message.usage.
  const inputT = m.input_tokens ?? parsed.usage?.input_tokens ?? 0;
  const outputT = m.output_tokens ?? parsed.usage?.output_tokens ?? 0;
  const cacheReadT = m.cache_read_input_tokens ?? parsed.usage?.cache_read_input_tokens ?? 0;
  const totalT = inputT + outputT;

  // "system" and "tool_result" rows collapse by default to keep the
  // scroll-scan focused on user prompts + assistant turns.
  const collapsedByDefault = role === "system" || role === "tool_result";

  const header = (
    <header className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-ink-muted">
      <span className="truncate">
        {role}
        {m.model ? ` · ${m.model}` : ""}
        {role === "assistant" && totalT > 0 ? (
          <span className="ml-1 text-ink-subtle normal-case tracking-normal">
            · {formatTokens(totalT)} tokens
            {cacheReadT > 0 ? ` · ${formatTokens(cacheReadT)} cached` : ""}
          </span>
        ) : null}
      </span>
      <time
        className="shrink-0 tabular-nums"
        title={new Date(m.timestamp).toLocaleString()}
        dateTime={m.timestamp}
      >
        {formatRelative(m.timestamp)}
      </time>
    </header>
  );

  const body = (
    <div className="space-y-2">
      {parsed.blocks.map((b, idx) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: block order is stable per message
        <Block key={idx} block={b} role={role} />
      ))}
    </div>
  );

  if (collapsedByDefault && parsed.blocks.length > 0) {
    return (
      <article
        data-role={role}
        data-testid="transcript-message"
        className={`rounded-md border-l-2 ${wrapperClass} pl-3 pr-2 py-2 space-y-2`}
      >
        {header}
        <details>
          <summary className="cursor-pointer text-[11px] text-ink-muted hover:text-ink py-1 min-h-9 inline-flex items-center">
            show {role.replace("_", " ")}
          </summary>
          <div className="mt-2">{body}</div>
        </details>
      </article>
    );
  }

  return (
    <article
      data-role={role}
      data-testid="transcript-message"
      className={`rounded-md border-l-2 ${wrapperClass} pl-3 pr-2 py-2 space-y-2`}
    >
      {header}
      {body}
    </article>
  );
}

function roleWrapperClass(role: string): string {
  switch (role) {
    case "user":
      return "border-teal/60 bg-teal-soft/30";
    case "assistant":
      return "border-ink-subtle/40 bg-surface";
    case "tool_result":
      return "border-info/40 bg-info/5";
    case "system":
      return "border-warn/40 bg-warn/5";
    default:
      return "border-line bg-surface-2";
  }
}

function Block({ block, role }: { block: ContentBlock; role: string }) {
  switch (block.type) {
    case "text":
      return <TextBody text={block.text} role={role} />;
    case "thinking":
      return <ThinkingChip text={block.text} />;
    case "tool_use":
      return <ToolUseChip block={block} />;
    case "tool_result":
      return (
        <ToolResultChip
          content={block.content}
          isError={block.is_error}
          toolUseId={block.tool_use_id}
        />
      );
    default:
      return (
        <pre className="text-[11px] font-mono text-ink-subtle whitespace-pre-wrap break-words">
          {JSON.stringify(block, null, 2)}
        </pre>
      );
  }
}

/**
 * Minimal markdown-ish renderer for plain text + triple-backtick code
 * fences. Handles:
 *
 *   - blank-line paragraph splits
 *   - single `\n` line breaks within a paragraph
 *   - ```lang\n...\n``` fences → `<pre>` blocks on the dark code surface
 *
 * Anything else (bold, italics, links, lists) renders as plain text — a
 * deliberate trade-off to avoid the dependency.
 */
function TextBody({ text, role }: { text: string; role: string }) {
  const segments = useMemo(() => splitFences(text), [text]);

  const baseTone =
    role === "user"
      ? "text-sm text-ink"
      : role === "assistant"
        ? "text-sm text-ink"
        : "text-sm text-ink-muted";

  return (
    <div className={`space-y-2 ${baseTone}`}>
      {segments.map((seg, i) =>
        seg.kind === "code" ? (
          <pre
            // biome-ignore lint/suspicious/noArrayIndexKey: order is stable from splitFences
            key={i}
            className="bg-code-bg text-code-text p-3 rounded-md text-[11px] leading-snug font-mono overflow-x-auto whitespace-pre"
          >
            {seg.text}
          </pre>
        ) : (
          // biome-ignore lint/suspicious/noArrayIndexKey: order is stable from splitFences
          <Paragraphs key={i} text={seg.text} />
        ),
      )}
    </div>
  );
}

function Paragraphs({ text }: { text: string }) {
  if (!text.trim()) return null;
  const paras = text.split(/\n{2,}/);
  return (
    <>
      {paras.map((p, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: paragraph order is stable per render
        <p key={i} className="whitespace-pre-wrap break-words">
          {p}
        </p>
      ))}
    </>
  );
}

type Segment = { kind: "text"; text: string } | { kind: "code"; text: string; lang?: string };

function splitFences(input: string): Segment[] {
  // Match triple-backtick blocks. Non-greedy so multiple fences don't merge.
  const re = /```(\w+)?\n?([\s\S]*?)```/g;
  const segments: Segment[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  // biome-ignore lint/suspicious/noAssignInExpressions: standard regex-walking loop
  while ((match = re.exec(input)) !== null) {
    if (match.index > last) {
      segments.push({ kind: "text", text: input.slice(last, match.index) });
    }
    segments.push({ kind: "code", text: match[2] ?? "", lang: match[1] });
    last = match.index + match[0].length;
  }
  if (last < input.length) {
    segments.push({ kind: "text", text: input.slice(last) });
  }
  if (segments.length === 0) segments.push({ kind: "text", text: input });
  return segments;
}

function ThinkingChip({ text }: { text: string }) {
  const tokensApprox = Math.max(1, Math.round(text.length / 4));
  return (
    <details className="rounded-md border border-line/60 bg-surface-2/40">
      <summary
        className="cursor-pointer text-[11px] text-ink-muted hover:text-ink px-2 py-1.5 min-h-9 inline-flex items-center gap-1.5"
        title="model chain-of-thought"
      >
        <span aria-hidden="true">💭</span>
        thought (~{formatTokens(tokensApprox)} chars, collapsed)
      </summary>
      <pre className="mt-1 px-3 pb-3 text-[12px] leading-snug font-mono text-ink-muted whitespace-pre-wrap break-words">
        {text}
      </pre>
    </details>
  );
}

function ToolUseChip({ block }: { block: ToolUseBlock }) {
  const summary = summarizeToolInput(block.name, block.input);
  const isDiff = block.name === "Edit" || block.name === "MultiEdit";
  const isWrite = block.name === "Write";

  // Pretty-printed input for the expanded body.
  const inputJson = useMemo(() => JSON.stringify(block.input, null, 2), [block.input]);

  return (
    <details className="rounded-md border border-line bg-surface-2/60">
      <summary className="cursor-pointer min-h-9 px-2 py-1.5 inline-flex items-center gap-2 text-[12px] text-ink hover:bg-surface-2 w-full">
        <span className="font-mono text-[11px] uppercase tracking-wide text-teal shrink-0">
          {block.name}
        </span>
        <span className="truncate text-ink-muted">{summary || <em>(no input)</em>}</span>
      </summary>
      <div className="px-2 pb-2 pt-1 space-y-2">
        {isDiff || isWrite ? (
          <ToolUseDiff name={block.name} input={block.input} />
        ) : (
          <pre className="bg-code-bg text-code-text p-2 rounded-md text-[11px] leading-snug font-mono overflow-x-auto whitespace-pre">
            {inputJson}
          </pre>
        )}
      </div>
    </details>
  );
}

function ToolUseDiff({ name, input }: { name: string; input: Record<string, unknown> }) {
  // For Edit / MultiEdit we drive DiffViewer with a synthetic unified diff
  // (- old_string / + new_string). For Write we pass the new file content
  // through as plain text.
  if (name === "Edit") {
    const oldStr = typeof input.old_string === "string" ? input.old_string : "";
    const newStr = typeof input.new_string === "string" ? input.new_string : "";
    const path = typeof input.file_path === "string" ? input.file_path : "(unknown path)";
    const synth = synthesiseDiff(path, oldStr, newStr);
    return <DiffViewer toolName="Edit" content={synth} />;
  }
  if (name === "MultiEdit") {
    const path = typeof input.file_path === "string" ? input.file_path : "(unknown path)";
    const edits = Array.isArray(input.edits) ? (input.edits as Array<Record<string, unknown>>) : [];
    const chunks = edits.map((e) => {
      const oldStr = typeof e.old_string === "string" ? e.old_string : "";
      const newStr = typeof e.new_string === "string" ? e.new_string : "";
      return synthesiseDiff(path, oldStr, newStr);
    });
    return <DiffViewer toolName="MultiEdit" content={chunks.join("\n")} />;
  }
  // Write — single-sided.
  const path = typeof input.file_path === "string" ? input.file_path : "(unknown path)";
  const content = typeof input.content === "string" ? input.content : JSON.stringify(input);
  return (
    <div className="space-y-1">
      <p className="text-[11px] text-ink-subtle font-mono">new file: {path}</p>
      <pre className="bg-code-bg text-code-text p-2 rounded-md text-[11px] leading-snug font-mono overflow-x-auto whitespace-pre">
        {content}
      </pre>
    </div>
  );
}

function synthesiseDiff(path: string, oldStr: string, newStr: string): string {
  const oldLines = oldStr.split("\n");
  const newLines = newStr.split("\n");
  const head = `--- ${path}\n+++ ${path}\n@@ -1,${oldLines.length} +1,${newLines.length} @@`;
  const minus = oldLines.map((l) => `-${l}`).join("\n");
  const plus = newLines.map((l) => `+${l}`).join("\n");
  return `${head}\n${minus}\n${plus}`;
}

function ToolResultChip({
  content,
  isError,
  toolUseId,
}: {
  content: string;
  isError?: boolean;
  toolUseId?: string;
}) {
  const tokensApprox = Math.max(1, Math.round(content.length / 4));
  // Short results inline; long ones collapse.
  const short = content.length < 200;
  const tone = isError ? "border-bad/40 text-bad" : "border-line text-ink-muted";
  const label = isError ? "→ error" : `→ result (~${formatTokens(tokensApprox)} chars)`;

  if (short) {
    return (
      <div
        className={`rounded-md border ${tone} px-2 py-1.5 text-[12px] font-mono whitespace-pre-wrap break-words`}
        data-tool-use-id={toolUseId}
      >
        <span className="text-ink-subtle text-[10px] mr-2 uppercase tracking-wide">
          {isError ? "error" : "result"}
        </span>
        {content || <em className="text-ink-subtle">(empty)</em>}
      </div>
    );
  }

  return (
    <details className={`rounded-md border ${tone} bg-surface-2/40`} data-tool-use-id={toolUseId}>
      <summary className="cursor-pointer min-h-9 px-2 py-1.5 inline-flex items-center gap-2 text-[12px]">
        <span className="font-mono">{label}</span>
      </summary>
      <pre className="px-3 pb-2 pt-1 text-[11px] leading-snug font-mono text-code-text bg-code-bg rounded-b-md overflow-x-auto whitespace-pre-wrap break-words">
        {content}
      </pre>
    </details>
  );
}
