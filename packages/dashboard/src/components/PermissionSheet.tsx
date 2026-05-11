import { useState } from "react";
import { Link } from "react-router";
import { ApiCallError, apiPost } from "../api/client";
import type { PermissionRequest } from "../api/types";

type Decision = "allow" | "deny" | "ask";

interface PermissionSheetProps {
  request: PermissionRequest;
  /** Called after a successful decision or after the user dismisses the sheet. */
  onClose: () => void;
  /** Optional toast/notify hook — bubbles up to the host page. */
  onDecided?: (req: PermissionRequest) => void;
}

const BTN_ALLOW =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium bg-emerald-500 text-emerald-950 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_ASK =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm text-zinc-200 border border-zinc-700 hover:bg-zinc-800/80 disabled:opacity-50 transition-colors";
const BTN_DENY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium text-red-300 border border-red-500/50 hover:bg-red-500/15 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

/**
 * V2.D4 — modal/drawer for deciding a single permission request.
 *
 * Renders the tool name, session deep-link, and pretty-printed tool_input.
 * Three buttons map to the backend's allow/deny/ask decisions; deny/ask
 * expose an optional reason textarea.
 *
 * Error handling:
 *   - 409 (already_decided)  → "Already decided — request expired", close
 *   - 404 (not_found)        → "Request no longer exists", close
 *   - anything else          → render inline error, keep modal open
 */
export default function PermissionSheet({ request, onClose, onDecided }: PermissionSheetProps) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [terminal, setTerminal] = useState<string | null>(null);

  const submit = async (decision: Decision) => {
    setError(null);
    setBusy(decision);
    try {
      const body: { decision: Decision; reason?: string } = { decision };
      if ((decision === "deny" || decision === "ask") && reason.trim()) {
        body.reason = reason.trim();
      }
      const updated = await apiPost<PermissionRequest>(
        `/api/permission-requests/${request.id}/decide`,
        body,
      );
      onDecided?.(updated);
      onClose();
    } catch (e) {
      if (e instanceof ApiCallError) {
        if (e.status === 409) {
          setTerminal("Already decided — request expired.");
          return;
        }
        if (e.status === 404) {
          setTerminal("Request no longer exists.");
          return;
        }
        setError(e.message);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-30 flex items-end sm:items-center justify-center p-0 sm:p-4"
      data-testid="permission-sheet"
    >
      <button
        type="button"
        aria-label="close permission sheet"
        onClick={onClose}
        className="absolute inset-0 bg-black/70 cursor-default"
      />
      <dialog
        open
        aria-modal="true"
        aria-label={`Permission request: ${request.tool_name}`}
        className="relative bg-zinc-950 border border-zinc-700 rounded-t-lg sm:rounded-md p-5 w-full sm:max-w-md max-h-[90vh] overflow-y-auto space-y-3 text-zinc-100"
      >
        <header className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-zinc-500">Permission request</p>
          <h3 className="text-base font-semibold inline-flex items-center gap-2">
            <span aria-hidden="true">🛂</span>
            <span className="truncate">{request.tool_name}</span>
          </h3>
          <Link
            to={`/sessions/${request.session_id}`}
            className="block text-[11px] text-emerald-300 hover:text-emerald-200 truncate"
            title={request.session_id}
          >
            session {request.session_id.slice(0, 12)}…
          </Link>
        </header>

        {terminal ? (
          <div
            role="alert"
            className="rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs px-3 py-2"
          >
            {terminal}
            <div className="mt-2">
              <button type="button" onClick={onClose} className={BTN_ASK}>
                Close
              </button>
            </div>
          </div>
        ) : (
          <>
            <section aria-label="tool input">
              <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">tool_input</p>
              <pre className="text-[11px] font-mono bg-zinc-900/80 border border-zinc-800 rounded p-2 max-h-48 overflow-auto whitespace-pre-wrap break-all">
                {prettyPrint(request.tool_input)}
              </pre>
            </section>

            <section aria-label="reason">
              <label
                htmlFor={`reason-${request.id}`}
                className="block text-[10px] uppercase tracking-wide text-zinc-500 mb-1"
              >
                Reason (optional, for deny/ask)
              </label>
              <textarea
                id={`reason-${request.id}`}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder="e.g. wrong directory"
                className="w-full px-3 py-2 rounded-md bg-zinc-900 border border-zinc-700 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500/60 focus:outline-none"
              />
            </section>

            {error ? (
              <p className="text-xs text-red-400" role="alert">
                {error}
              </p>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => submit("allow")}
                className={BTN_ALLOW}
              >
                {busy === "allow" ? "Allowing…" : "Allow"}
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => submit("ask")}
                className={BTN_ASK}
              >
                {busy === "ask" ? "Asking…" : "Ask"}
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => submit("deny")}
                className={BTN_DENY}
              >
                {busy === "deny" ? "Denying…" : "Deny"}
              </button>
              <button
                type="button"
                onClick={onClose}
                disabled={busy !== null}
                className="ml-auto text-xs text-zinc-400 hover:text-zinc-200 px-2 py-1"
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}

function prettyPrint(input: unknown): string {
  if (input === null || input === undefined) return "(no input)";
  if (typeof input === "string") return input;
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}
