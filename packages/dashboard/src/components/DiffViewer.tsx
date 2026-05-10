interface DiffViewerProps {
  /** Tool name; informs styling (Edit/Write → diff, Bash → pre, Read → collapsed). */
  toolName?: string;
  /** Raw content body. */
  content: string;
  /** When true, wrap in <details> closed by default. */
  collapsed?: boolean;
  className?: string;
}

/**
 * Lightweight tool-output viewer. Uses CSS only — no syntax-highlighter dep.
 *
 * For Edit / Write / MultiEdit we tint added / removed / hunk-header lines
 * inline. The heuristic is the standard unified-diff prefix:
 *   `+ ` → added, `- ` → removed, `@@` → hunk header. Anything else passes
 * through plain. JSON-style payloads from `tool_use` blocks (e.g.
 * `Edit: {"path":…,"old_string":…,"new_string":…}`) won't have those
 * prefixes and just render as monospace text — better than nothing and
 * graceful when the format isn't a real diff.
 *
 * Bash uses a darker terminal-style block. Read tool results render as
 * collapsed details so they don't dominate the transcript.
 */
export default function DiffViewer({
  toolName,
  content,
  collapsed = false,
  className = "",
}: DiffViewerProps) {
  const isDiff = toolName === "Edit" || toolName === "Write" || toolName === "MultiEdit";
  const isBash = toolName === "Bash";

  const body = isDiff ? (
    <DiffPre content={content} className={className} />
  ) : (
    <pre
      className={`whitespace-pre-wrap break-words text-[11px] leading-snug font-mono p-2 rounded-md ${
        isBash
          ? "bg-black text-emerald-200 border border-zinc-800"
          : "bg-zinc-900 text-zinc-300 border border-zinc-800"
      } ${className}`}
    >
      {content}
    </pre>
  );

  if (!collapsed) return body;

  return (
    <details className="rounded-md">
      <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-200 py-2 min-h-11 inline-flex items-center">
        {toolName ?? "tool output"} (click to expand)
      </summary>
      <div className="mt-1">{body}</div>
    </details>
  );
}

function DiffPre({ content, className = "" }: { content: string; className?: string }) {
  const lines = content.split("\n");
  // If the content has at least one diff-marker line, treat it as a diff and
  // render with line numbers + tints. Otherwise fall back to a monospace pre
  // (which still beats no formatting for tool-call JSON payloads).
  const looksLikeDiff = lines.some(
    (l) => l.startsWith("+") || l.startsWith("-") || l.startsWith("@@"),
  );
  if (!looksLikeDiff) {
    return (
      <pre
        className={`whitespace-pre-wrap break-words text-[11px] leading-snug font-mono p-2 rounded-md bg-zinc-900 text-zinc-200 border border-zinc-800 ${className}`}
      >
        {content}
      </pre>
    );
  }

  const widthCh = String(lines.length).length;
  return (
    <div
      className={`text-[11px] leading-snug font-mono rounded-md bg-zinc-900 border border-zinc-800 overflow-x-auto ${className}`}
    >
      <ol className="min-w-full">
        {lines.map((raw, i) => {
          const tint = lineTint(raw);
          return (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: line index IS the stable identity here
              key={i}
              className={`flex items-start whitespace-pre ${tint.row}`}
            >
              <span
                aria-hidden="true"
                className="select-none px-2 py-0.5 text-zinc-600 text-right shrink-0 border-r border-zinc-800/80"
                style={{ minWidth: `${widthCh + 1}ch` }}
              >
                {i + 1}
              </span>
              <span className={`flex-1 px-2 py-0.5 break-words ${tint.text}`}>{raw || " "}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function lineTint(line: string): { row: string; text: string } {
  // Hunk header `@@ -1,3 +1,4 @@` — soft purple/zinc.
  if (line.startsWith("@@")) return { row: "bg-zinc-800/40", text: "text-zinc-400" };
  // Added — soft green tint, brighter text.
  if (line.startsWith("+") && !line.startsWith("+++"))
    return { row: "bg-emerald-500/10", text: "text-emerald-200" };
  // Removed — soft red tint.
  if (line.startsWith("-") && !line.startsWith("---"))
    return { row: "bg-red-500/10", text: "text-red-200" };
  // File header lines (+++ / ---) — dim.
  if (line.startsWith("+++") || line.startsWith("---")) return { row: "", text: "text-zinc-500" };
  return { row: "", text: "text-zinc-300" };
}
