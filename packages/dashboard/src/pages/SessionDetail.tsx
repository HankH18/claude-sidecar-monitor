import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import ActivityLine from "../components/ActivityLine";
import AgentKindIcon from "../components/AgentKindIcon";
import Breadcrumbs from "../components/Breadcrumbs";
import DiffViewer from "../components/DiffViewer";
import ElapsedClock from "../components/ElapsedClock";
import EmptyState from "../components/EmptyState";
import SessionLabel from "../components/SessionLabel";
import StatePill from "../components/StatePill";
import TokenBadge from "../components/TokenBadge";
import Window from "../components/Window";

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
      className="inline-flex items-center justify-center min-h-9 min-w-11 px-2 text-[11px] text-ink-muted hover:text-ink rounded border border-line hover:bg-surface-2"
      aria-label={copied ? "copied" : "copy message"}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function TimelineStrip({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-[11px] text-ink-muted px-1">No events yet.</p>;
  }
  return (
    <div className="overflow-x-auto -mx-1 px-1" aria-label="event timeline">
      <ol className="flex items-stretch gap-1 min-w-max">
        {entries.map((e) => {
          const isPre = e.event_name === "PreToolUse";
          const isPost = e.event_name === "PostToolUse";
          const color = isPre
            ? "bg-good/15 text-good border-good/40"
            : isPost
              ? "bg-info/15 text-info border-info/40"
              : "bg-surface-2 text-ink-muted border-line";
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
    user: "border-teal/40 bg-teal-soft/40",
    assistant: "border-line bg-surface",
    tool_result: "border-info/30 bg-info/5",
    system: "border-warn/30 bg-warn/5",
  }[m.role];

  const isToolIO = m.role === "tool_result" || (m.role === "assistant" && m.tool_name);
  const isReadResult = m.tool_name === "Read";

  return (
    <article
      className={`rounded-md border ${roleColor} p-3 space-y-2`}
      data-role={m.role}
      data-testid="transcript-message"
    >
      <header className="flex items-center justify-between text-[10px] uppercase tracking-wide text-ink-muted">
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
        <p className="text-sm text-ink whitespace-pre-wrap">{m.content}</p>
      )}
    </article>
  );
}

function SkeletonDetail() {
  return (
    <div className="space-y-4" aria-busy="true">
      {/* back link + title row */}
      <div className="space-y-2">
        <div className="h-3 w-12 rounded bg-line/60 animate-pulse" />
        <div className="flex items-center justify-between gap-2">
          <div className="space-y-1.5 flex-1">
            <div className="h-5 w-32 rounded bg-line/60 animate-pulse" />
            <div className="h-3 w-48 rounded bg-line/40 animate-pulse" />
          </div>
          <div className="h-6 w-20 rounded-full bg-line/60 animate-pulse" />
        </div>
        <div className="flex items-center justify-between">
          <div className="h-3 w-12 rounded bg-line/40 animate-pulse" />
          <div className="space-y-1">
            <div className="h-3 w-20 rounded bg-line/60 animate-pulse" />
            <div className="h-2 w-12 rounded bg-line/40 animate-pulse" />
          </div>
        </div>
      </div>
      {/* timeline */}
      <div className="flex gap-1 overflow-hidden">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-9 w-16 rounded bg-line/50 animate-pulse" />
        ))}
      </div>
      {/* transcript blocks */}
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 rounded-md bg-line/40 animate-pulse" />
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
    return <p className="text-sm text-ink-muted">No session id.</p>;
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
          <Link to="/" className="text-xs text-teal hover:text-cta hover:underline">
            ← back
          </Link>
          <p className="text-sm text-bad">Failed to load session: {liveError}</p>
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <Link
          to="/"
          className="inline-flex items-center gap-1 min-h-11 -mx-1 px-1 text-xs text-teal hover:text-cta"
        >
          <span aria-hidden="true">←</span> back
        </Link>
        <p className="text-sm text-ink-muted">Session not found.</p>
      </div>
    );
  }

  const live = session.state === "running" || session.state === "tool";

  // Breadcrumbs: Live › <project> › <agent_type>. The middle crumb deep-links
  // to /projects/<encoded> so the user can navigate up one level instead of
  // landing back at the Live overview.
  const projectLabel =
    session.project_label ?? session.worktree_root.split("/").pop() ?? session.worktree_root;
  const projectHref = `/projects/${encodeURIComponent(session.worktree_root)}`;

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Live", to: "/" },
          { label: projectLabel, to: projectHref },
          {
            label: session.title ?? session.nickname ?? session.agent_type ?? "session",
            display: (
              <span className="inline-flex items-center gap-1.5 min-w-0">
                <AgentKindIcon
                  kind={session.agent_kind ?? null}
                  confidence={session.agent_kind_confidence ?? null}
                  className="text-[11px]"
                />
                <SessionLabel session={session} className="truncate" />
              </span>
            ),
          },
        ]}
      />

      <Window
        icon="doc"
        title={session.title ?? session.nickname ?? session.agent_type ?? "session"}
        aria-label="session metadata"
        actions={<StatePill state={session.state} />}
      >
        <div className="space-y-2">
          <h1 className="text-base font-semibold text-ink truncate inline-flex items-center gap-1.5">
            <AgentKindIcon
              kind={session.agent_kind ?? null}
              confidence={session.agent_kind_confidence ?? null}
              className="shrink-0"
            />
            <SessionLabel session={session} className="truncate" />
          </h1>
          <ActivityLine
            summary={session.activity_summary ?? null}
            updatedAt={session.activity_updated_at ?? null}
          />
          <p className="text-[11px] text-ink-muted truncate">
            {session.project_label ?? session.worktree_root}
          </p>
          <div className="flex items-center justify-between text-xs text-ink-muted pt-1 border-t border-line">
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
        </div>
      </Window>

      <Window icon="doc" title="Timeline" aria-label="event timeline">
        <h2 className="sr-only">Timeline</h2>
        <TimelineStrip entries={timeline} />
      </Window>

      <Window icon="transcript" title="Transcript" aria-label="transcript" bodyClassName="p-3">
        <h2 className="sr-only">Transcript</h2>
        {transcript.length === 0 ? (
          <EmptyState
            illustration="transcript"
            title="No transcript yet"
            message="Once the agent emits its first turn, prompts and tool I/O stream in here."
          />
        ) : (
          <Transcript transcript={transcript} />
        )}
      </Window>
    </div>
  );
}

/**
 * Transcript with a right-edge sticky scrubber + jump-to-latest CTA + j/k
 * keyboard navigation. Splitting this into its own component keeps the
 * (otherwise large) parent focused on data fetching.
 */
function Transcript({ transcript }: { transcript: TranscriptMessage[] }) {
  const refs = useRef<Array<HTMLElement | null>>([]);
  const [activeIndex, setActiveIndex] = useState(transcript.length - 1);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  // Keep the refs array in sync with the transcript length so callbacks
  // never read past the end.
  if (refs.current.length !== transcript.length) {
    refs.current = transcript.map((_, i) => refs.current[i] ?? null);
  }

  const scrollToIndex = useCallback((idx: number) => {
    const el = refs.current[idx];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  // j / k step through messages. Skip when the user is typing in an input.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (
        tag === "input" ||
        tag === "textarea" ||
        (e.target as HTMLElement | null)?.isContentEditable
      )
        return;
      if (e.key === "j") {
        e.preventDefault();
        setActiveIndex((i) => {
          const next = Math.min(transcript.length - 1, i + 1);
          scrollToIndex(next);
          return next;
        });
      } else if (e.key === "k") {
        e.preventDefault();
        setActiveIndex((i) => {
          const next = Math.max(0, i - 1);
          scrollToIndex(next);
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [transcript.length, scrollToIndex]);

  // Watch the last message's visibility so we can flip "jump to latest" on/off.
  useEffect(() => {
    if (transcript.length === 0) return;
    const last = refs.current[transcript.length - 1];
    if (!last || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          setShowJumpToLatest(!entry.isIntersecting);
        }
      },
      { threshold: 0.05 },
    );
    obs.observe(last);
    return () => obs.disconnect();
  }, [transcript.length]);

  return (
    <div className="relative flex gap-2">
      <div className="flex-1 min-w-0 space-y-3" data-testid="transcript-list">
        {transcript.map((m, i) => (
          <div
            key={m.message_id}
            ref={(el) => {
              refs.current[i] = el;
            }}
          >
            <MessageBlock m={m} />
          </div>
        ))}
      </div>

      <Scrubber
        transcript={transcript}
        activeIndex={activeIndex}
        onJump={(i) => {
          setActiveIndex(i);
          scrollToIndex(i);
        }}
      />

      {showJumpToLatest ? (
        <button
          type="button"
          onClick={() => {
            const last = transcript.length - 1;
            setActiveIndex(last);
            scrollToIndex(last);
          }}
          className="fixed bottom-4 right-4 z-10 inline-flex items-center min-h-11 px-3 rounded-full bg-cta text-white text-xs font-medium shadow-lg hover:bg-cta-hover active:translate-y-px"
          data-testid="jump-to-latest"
        >
          ↓ Jump to latest
        </button>
      ) : null}
    </div>
  );
}

/**
 * Sticky right-edge scrubber. Each marker is one transcript message; the
 * letter codes (U/A/T/S) come from the role so the user can scan to a
 * specific kind of turn (skip past tool results to the next user prompt).
 */
function Scrubber({
  transcript,
  activeIndex,
  onJump,
}: {
  transcript: TranscriptMessage[];
  activeIndex: number;
  onJump(i: number): void;
}) {
  if (transcript.length <= 4) return null; // not worth the chrome
  return (
    <nav
      aria-label="transcript scrubber"
      className="sticky top-28 self-start shrink-0 hidden sm:flex flex-col gap-0.5 max-h-[60vh] overflow-y-auto pr-1"
      data-testid="transcript-scrubber"
    >
      {transcript.map((m, i) => {
        const code = roleCode(m.role);
        const tone = roleTone(m.role);
        const active = i === activeIndex;
        return (
          <button
            key={m.message_id}
            type="button"
            onClick={() => onJump(i)}
            aria-label={`jump to message ${i + 1} (${m.role})`}
            className={`min-h-6 min-w-6 px-1 inline-flex items-center justify-center text-[9px] font-mono rounded ${tone} ${active ? "ring-1 ring-teal" : ""}`}
          >
            {code}
          </button>
        );
      })}
    </nav>
  );
}

function roleCode(role: TranscriptMessage["role"]): string {
  switch (role) {
    case "user":
      return "U";
    case "assistant":
      return "A";
    case "tool_result":
      return "T";
    case "system":
      return "S";
  }
}

function roleTone(role: TranscriptMessage["role"]): string {
  switch (role) {
    case "user":
      return "bg-teal-soft text-ink";
    case "assistant":
      return "bg-surface-2 text-ink-muted";
    case "tool_result":
      return "bg-info/15 text-info";
    case "system":
      return "bg-warn/15 text-warn";
  }
}
