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
 * Pretty-printed tool I/O. Intentionally framework-light — no syntax highlighter
 * dependency in v0.1; relies on monospace + whitespace-pre-wrap.
 */
export default function DiffViewer({
  toolName,
  content,
  collapsed = false,
  className = "",
}: DiffViewerProps) {
  const isDiff = toolName === "Edit" || toolName === "Write" || toolName === "MultiEdit";
  const isBash = toolName === "Bash";

  const body = (
    <pre
      className={`whitespace-pre-wrap break-words text-[11px] leading-snug font-mono p-2 rounded-md ${
        isDiff
          ? "bg-zinc-900 text-zinc-200 border border-zinc-800"
          : isBash
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
      <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-200 py-1">
        {toolName ?? "tool output"} (click to expand)
      </summary>
      <div className="mt-1">{body}</div>
    </details>
  );
}
