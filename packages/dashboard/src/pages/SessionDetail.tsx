import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import {
  type TimelineEntry,
  type TranscriptMessage,
  mockSessions,
  mockTimeline,
  mockTranscript,
} from "../api/mock";
import { useMock } from "../api/mode";
import type { Session } from "../api/types";
import DiffViewer from "../components/DiffViewer";
import ElapsedClock from "../components/ElapsedClock";
import StatePill from "../components/StatePill";
import TokenBadge from "../components/TokenBadge";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          // Clipboard may not be available (test env). Silently fail.
        }
      }}
      className="text-[10px] text-zinc-500 hover:text-zinc-200 px-1.5 py-0.5 rounded border border-zinc-800"
      aria-label="copy"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function TimelineStrip({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-[11px] text-zinc-600">No events yet.</p>;
  }
  return (
    <div className="overflow-x-auto -mx-1 px-1" aria-label="event timeline">
      <ol className="flex items-stretch gap-1 min-w-max">
        {entries.map((e) => {
          const isPre = e.event_name === "PreToolUse";
          const isPost = e.event_name === "PostToolUse";
          const color = isPre
            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
            : isPost
              ? "bg-blue-500/15 text-blue-300 border-blue-500/40"
              : "bg-zinc-800/60 text-zinc-300 border-zinc-700";
          return (
            <li
              key={e.event_id}
              className={`text-[10px] font-mono px-2 py-1 rounded border ${color}`}
            >
              <div>{e.tool_name ?? e.event_name}</div>
              {e.duration_ms !== undefined ? (
                <div className="text-[9px] opacity-80">{e.duration_ms} ms</div>
              ) : (
                <div className="text-[9px] opacity-80">
                  {new Date(e.timestamp).toLocaleTimeString()}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function MessageBlock({ m }: { m: TranscriptMessage }) {
  const roleColor = {
    user: "border-emerald-500/40 bg-emerald-500/5",
    assistant: "border-zinc-700 bg-zinc-900/60",
    tool_result: "border-blue-500/30 bg-blue-500/5",
    system: "border-yellow-500/30 bg-yellow-500/5",
  }[m.role];

  const isToolIO = m.role === "tool_result" || (m.role === "assistant" && m.tool_name);
  const isReadResult = m.tool_name === "Read";

  return (
    <article
      className={`rounded-md border ${roleColor} p-3 space-y-2`}
      data-role={m.role}
      data-testid="transcript-message"
    >
      <header className="flex items-center justify-between text-[10px] uppercase tracking-wide text-zinc-500">
        <span>
          {m.role}
          {m.tool_name ? ` · ${m.tool_name}` : ""}
          {m.model ? ` · ${m.model}` : ""}
        </span>
        <div className="flex items-center gap-1">
          <span>{new Date(m.timestamp).toLocaleTimeString()}</span>
          <CopyButton text={m.content} />
        </div>
      </header>
      {isToolIO ? (
        <DiffViewer toolName={m.tool_name} content={m.content} collapsed={isReadResult} />
      ) : (
        <p className="text-sm text-zinc-200 whitespace-pre-wrap">{m.content}</p>
      )}
    </article>
  );
}

export default function SessionDetail() {
  const { id } = useParams();
  const mock = useMock();

  const session: Session | null = useMemo(() => {
    if (!id) return null;
    if (mock) {
      return mockSessions.find((s) => s.session_id === id) ?? null;
    }
    // The real fetch would happen here via apiGet<SessionDetail>(`/api/sessions/${id}`).
    // v0.1 deliberately keeps this page mock-only for the dashboard sub-agent.
    return null;
  }, [id, mock]);

  const transcript = useMemo<TranscriptMessage[]>(() => {
    if (!id) return [];
    return mock ? mockTranscript(id) : [];
  }, [id, mock]);

  const timeline = useMemo<TimelineEntry[]>(() => {
    if (!id) return [];
    return mock ? mockTimeline(id) : [];
  }, [id, mock]);

  if (!id) {
    return <p className="text-sm text-zinc-500">No session id.</p>;
  }

  if (!session) {
    return (
      <div className="space-y-2">
        <Link to="/" className="text-xs text-emerald-400 hover:underline">
          ← back
        </Link>
        <p className="text-sm text-zinc-500">Session not found.</p>
      </div>
    );
  }

  const live = session.state === "running" || session.state === "tool";

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <Link to="/" className="text-xs text-emerald-400 hover:underline">
          ← back
        </Link>
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-zinc-100 truncate">
              {session.agent_type ?? "session"}
            </h1>
            <p className="text-[11px] text-zinc-500 truncate">
              {session.project_label ?? session.worktree_root}
            </p>
          </div>
          <StatePill state={session.state} />
        </div>
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span>
            <ElapsedClock since={session.started_at} live={live} />
          </span>
          <TokenBadge
            input={session.input_tokens}
            output={session.output_tokens}
            cacheRead={session.cache_read_tokens}
            cacheWrite={session.cache_write_tokens}
          />
        </div>
      </header>

      <section aria-label="event timeline" className="space-y-1">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500">Timeline</h2>
        <TimelineStrip entries={timeline} />
      </section>

      <section aria-label="transcript" className="space-y-2">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500">Transcript</h2>
        {transcript.length === 0 ? (
          <p className="text-sm text-zinc-600">No transcript yet.</p>
        ) : (
          <div className="space-y-2">
            {transcript.map((m) => (
              <MessageBlock key={m.message_id} m={m} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
