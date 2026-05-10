import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiCallError, apiGet, withRetry } from "../api/client";
import {
  type TimelineEntry,
  type TranscriptMessage,
  mockSessions,
  mockTimeline,
  mockTranscript,
} from "../api/mock";
import { useMock } from "../api/mode";
import type { Session, SessionDetail as SessionDetailT } from "../api/types";
import DiffViewer from "../components/DiffViewer";
import ElapsedClock from "../components/ElapsedClock";
import EmptyState from "../components/EmptyState";
import StatePill from "../components/StatePill";
import TokenBadge from "../components/TokenBadge";

interface RawTranscriptMessage {
  message_id: number;
  session_id: string;
  role: string;
  timestamp: string;
  content_json: string;
  model?: string | null;
}

interface TranscriptPage {
  messages: RawTranscriptMessage[];
  next_cursor: number | null;
}

/** Server transcript rows store JSON-stringified content; flatten to a string. */
function flattenContent(contentJson: string): {
  content: string;
  toolName?: string;
  isDiff?: boolean;
} {
  try {
    const parsed = JSON.parse(contentJson) as unknown;
    if (typeof parsed === "string") return { content: parsed };
    if (Array.isArray(parsed)) {
      // Anthropic content blocks: [{type:"text",text:...}, {type:"tool_use",name,input}, ...]
      const parts: string[] = [];
      let toolName: string | undefined;
      let isDiff = false;
      for (const block of parsed as Array<Record<string, unknown>>) {
        const type = block.type;
        if (type === "text" && typeof block.text === "string") {
          parts.push(block.text);
        } else if (type === "tool_use") {
          toolName = (block.name as string) || toolName;
          if (toolName === "Edit" || toolName === "Write") isDiff = true;
          parts.push(`${toolName ?? "tool"}: ${JSON.stringify(block.input ?? {})}`);
        } else if (type === "tool_result") {
          const c = block.content;
          if (typeof c === "string") parts.push(c);
          else parts.push(JSON.stringify(c));
        } else if (typeof block.text === "string") {
          parts.push(block.text);
        }
      }
      return { content: parts.join("\n"), toolName, isDiff };
    }
    return { content: JSON.stringify(parsed) };
  } catch {
    return { content: contentJson };
  }
}

function toUiMessage(raw: RawTranscriptMessage): TranscriptMessage {
  const role = (
    raw.role === "user" || raw.role === "assistant" || raw.role === "system"
      ? raw.role
      : "tool_result"
  ) as TranscriptMessage["role"];
  const flat = flattenContent(raw.content_json);
  return {
    message_id: raw.message_id,
    role,
    timestamp: raw.timestamp,
    content: flat.content,
    model: raw.model ?? undefined,
    tool_name: flat.toolName,
    is_diff: flat.isDiff,
  };
}

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
      className="inline-flex items-center justify-center min-h-9 min-w-11 px-2 text-[11px] text-zinc-400 hover:text-zinc-100 rounded border border-zinc-800 hover:bg-zinc-800/60"
      aria-label={copied ? "copied" : "copy message"}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function TimelineStrip({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-[11px] text-zinc-600 px-1">No events yet.</p>;
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
              className={`text-[10px] font-mono px-2 py-1.5 rounded border ${color}`}
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

function SkeletonDetail() {
  return (
    <div className="space-y-4" aria-busy="true">
      {/* back link + title row */}
      <div className="space-y-2">
        <div className="h-3 w-12 rounded bg-zinc-800/60 animate-pulse" />
        <div className="flex items-center justify-between gap-2">
          <div className="space-y-1.5 flex-1">
            <div className="h-5 w-32 rounded bg-zinc-800/60 animate-pulse" />
            <div className="h-3 w-48 rounded bg-zinc-800/40 animate-pulse" />
          </div>
          <div className="h-6 w-20 rounded-full bg-zinc-800/60 animate-pulse" />
        </div>
        <div className="flex items-center justify-between">
          <div className="h-3 w-12 rounded bg-zinc-800/40 animate-pulse" />
          <div className="space-y-1">
            <div className="h-3 w-20 rounded bg-zinc-800/60 animate-pulse" />
            <div className="h-2 w-12 rounded bg-zinc-800/40 animate-pulse" />
          </div>
        </div>
      </div>
      {/* timeline */}
      <div className="flex gap-1 overflow-hidden">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-9 w-16 rounded bg-zinc-800/50 animate-pulse" />
        ))}
      </div>
      {/* transcript blocks */}
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 rounded-md bg-zinc-800/40 animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export default function SessionDetail() {
  const { id } = useParams();
  const mock = useMock();

  // Mock-mode: synchronous lookups against fixtures.
  const mockSession: Session | null = useMemo(() => {
    if (!id || !mock) return null;
    return mockSessions.find((s) => s.session_id === id) ?? null;
  }, [id, mock]);

  const mockTranscriptMsgs = useMemo<TranscriptMessage[]>(() => {
    if (!id || !mock) return [];
    return mockTranscript(id);
  }, [id, mock]);

  const mockTimelineEntries = useMemo<TimelineEntry[]>(() => {
    if (!id || !mock) return [];
    return mockTimeline(id);
  }, [id, mock]);

  // Live-mode state.
  const [liveSession, setLiveSession] = useState<Session | null>(null);
  const [liveTranscript, setLiveTranscript] = useState<TranscriptMessage[]>([]);
  const [liveLoading, setLiveLoading] = useState(true);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [liveNotFound, setLiveNotFound] = useState(false);

  useEffect(() => {
    if (mock || !id) return;
    let cancelled = false;
    setLiveLoading(true);
    setLiveError(null);
    setLiveNotFound(false);
    setLiveSession(null);
    setLiveTranscript([]);

    (async () => {
      try {
        const [session, page] = await Promise.all([
          withRetry(() => apiGet<SessionDetailT>(`/api/sessions/${id}`)),
          withRetry(() => apiGet<TranscriptPage>(`/api/sessions/${id}/transcript`)).catch((err) => {
            // If transcript 404s but session is fine, render empty list.
            if (err instanceof ApiCallError && err.status === 404) {
              return { messages: [], next_cursor: null } as TranscriptPage;
            }
            throw err;
          }),
        ]);
        if (cancelled) return;
        setLiveSession(session);
        setLiveTranscript(page.messages.map(toUiMessage));
        setLiveLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiCallError && err.status === 404) {
          setLiveNotFound(true);
        } else {
          setLiveError((err as Error).message);
        }
        setLiveLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, mock]);

  if (!id) {
    return <p className="text-sm text-zinc-500">No session id.</p>;
  }

  if (!mock && liveLoading) {
    return <SkeletonDetail />;
  }

  const session = mock ? mockSession : liveSession;
  const transcript = mock ? mockTranscriptMsgs : liveTranscript;
  const timeline = mock ? mockTimelineEntries : [];

  const notFound = mock ? !session : liveNotFound;

  if (notFound || !session) {
    if (!mock && liveError) {
      return (
        <div className="space-y-2">
          <Link to="/" className="text-xs text-emerald-400 hover:underline">
            ← back
          </Link>
          <p className="text-sm text-red-400">Failed to load session: {liveError}</p>
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <Link
          to="/"
          className="inline-flex items-center gap-1 min-h-11 -mx-1 px-1 text-xs text-emerald-300 hover:text-emerald-200"
        >
          <span aria-hidden="true">←</span> back
        </Link>
        <p className="text-sm text-zinc-500">Session not found.</p>
      </div>
    );
  }

  const live = session.state === "running" || session.state === "tool";

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <Link
          to="/"
          className="inline-flex items-center gap-1 min-h-11 -mx-1 px-1 text-xs text-emerald-300 hover:text-emerald-200"
        >
          <span aria-hidden="true">←</span> back
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
          <EmptyState
            illustration="transcript"
            title="No transcript yet"
            message="Once the agent emits its first turn, prompts and tool I/O will stream in here in real time."
          />
        ) : (
          <div className="space-y-3">
            {transcript.map((m) => (
              <MessageBlock key={m.message_id} m={m} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
