import { type ReactElement, memo } from "react";
import type { Session } from "../api/types";

interface SessionLabelProps {
  session: Pick<Session, "session_id" | "title" | "nickname" | "agent_type">;
  /** Tailwind utilities for the outer span. */
  className?: string;
  /** Force a leading icon (e.g. virtual subagent glyph). */
  prefix?: ReactElement | null;
  /** Optional override — when omitted we derive a short fallback. */
  fallback?: string;
}

/**
 * Render priority (highest to lowest):
 *   1. `title` (V2.A3 derived from user prompt, ≤80 chars)
 *   2. `nickname` (V2.A3 adj-noun-NNNN)
 *   3. `agent_type` (v1 label)
 *   4. shortened session_id (first 8 chars)
 *
 * Title tooltip always shows the full session_id so the user can copy it
 * out of dev tools / inspect without needing a separate "show id" UI.
 *
 * Memoized because TreeRow re-renders on every arborist toggle.
 */
function SessionLabelInner({ session, className, prefix, fallback }: SessionLabelProps) {
  const text =
    session.title?.trim() ||
    session.nickname?.trim() ||
    session.agent_type?.trim() ||
    fallback ||
    session.session_id.slice(0, 8);
  return (
    <span
      className={className}
      title={session.session_id}
      data-testid="session-label"
      data-source={
        session.title
          ? "title"
          : session.nickname
            ? "nickname"
            : session.agent_type
              ? "agent_type"
              : "session_id"
      }
    >
      {prefix}
      {text}
    </span>
  );
}

const SessionLabel = memo(SessionLabelInner);
export default SessionLabel;
