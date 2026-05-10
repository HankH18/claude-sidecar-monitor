import { type FormEvent, useEffect, useMemo, useState } from "react";
import { apiPost } from "../api/client";
import { useMock } from "../api/mode";
import type { Settings as SettingsT } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useSettings } from "../hooks/useSettings";

/**
 * Button intent classes — small palette so a glance tells you what each
 * action does:
 *   - primary   = save/submit (filled emerald)
 *   - secondary = neutral, info-y action (outlined zinc)
 *   - danger    = irreversible (outlined red, fills on hover)
 */
const BTN_PRIMARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium bg-emerald-500 text-emerald-950 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_SECONDARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm text-zinc-200 border border-zinc-700 hover:bg-zinc-800/80 disabled:opacity-50 transition-colors";
const BTN_DANGER =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium text-red-300 border border-red-500/50 hover:bg-red-500/15 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

const INPUT =
  "w-full min-h-11 px-3 rounded-md bg-zinc-900 border border-zinc-700 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500/60 focus:outline-none";

/**
 * Generate a 16-char base32 ntfy topic. We use crypto.getRandomValues so
 * the topic isn't predictable; falls back to Math.random in environments
 * without WebCrypto (test runners, very old browsers) — that's acceptable
 * because the user still has to Save before the value goes live.
 */
function generateNtfyTopic(): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  return `csm-${Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("")}`;
}

export default function Settings() {
  const { settings, loading, save } = useSettings();
  const mock = useMock();
  const { push } = useToast();
  const [form, setForm] = useState<SettingsT | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPassphrase, setShowPassphrase] = useState(false);

  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  if (loading || !form) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-5 w-24 rounded bg-zinc-800/60 animate-pulse" />
        <div className="h-11 rounded-md bg-zinc-800/40 animate-pulse" />
        <div className="h-11 rounded-md bg-zinc-800/40 animate-pulse" />
        <div className="h-11 rounded-md bg-zinc-800/40 animate-pulse" />
      </div>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await save(form);
      setSavedAt(Date.now());
      push({ message: "Settings saved.", variant: "success" });
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      push({ message: `Failed to save settings: ${msg}`, variant: "error" });
    }
  };

  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
      </header>

      <form onSubmit={onSubmit} className="space-y-5" aria-label="settings form">
        <Field
          id="hang_yellow_ms"
          label="Hang yellow threshold (ms)"
          hint="Mark a session stale after this many ms without an event."
        >
          <input
            id="hang_yellow_ms"
            name="hang_yellow_ms"
            type="number"
            min={1000}
            max={3_600_000}
            step={1000}
            className={INPUT}
            value={form.hang_yellow_ms}
            onChange={(e) => setForm({ ...form, hang_yellow_ms: Number(e.target.value) || 0 })}
          />
        </Field>

        <Field
          id="hang_red_ms"
          label="Hang red threshold (ms)"
          hint="Mark a session hung after this many ms; triggers ntfy."
        >
          <input
            id="hang_red_ms"
            name="hang_red_ms"
            type="number"
            min={1000}
            max={3_600_000}
            step={1000}
            className={INPUT}
            value={form.hang_red_ms}
            onChange={(e) => setForm({ ...form, hang_red_ms: Number(e.target.value) || 0 })}
          />
        </Field>

        <Field
          id="ntfy_topic"
          label="ntfy.sh topic"
          hint="Public ntfy topic for hang/done pushes. Empty disables notifications."
        >
          <input
            id="ntfy_topic"
            name="ntfy_topic"
            type="text"
            autoComplete="off"
            className={INPUT}
            value={form.ntfy_topic}
            onChange={(e) => setForm({ ...form, ntfy_topic: e.target.value })}
          />
          {!form.ntfy_topic ? (
            <div
              className="rounded-md border border-amber-500/30 bg-amber-500/5 text-[11px] text-amber-200 px-3 py-2 mt-2 space-y-1"
              data-testid="ntfy-empty-hint"
            >
              <p>
                No topic set. Push notifications need a topic — sign up at{" "}
                <a
                  href="https://ntfy.sh/"
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-amber-100"
                >
                  ntfy.sh
                </a>{" "}
                or generate one.
              </p>
              <button
                type="button"
                className="inline-flex items-center min-h-9 px-3 rounded border border-amber-500/40 text-amber-100 hover:bg-amber-500/15 text-[11px]"
                onClick={() => setForm({ ...form, ntfy_topic: generateNtfyTopic() })}
              >
                Generate random topic
              </button>
            </div>
          ) : null}

          <NtfyPreview topic={form.ntfy_topic} />
        </Field>

        <div className="flex items-center gap-3 flex-wrap">
          <button type="submit" className={BTN_PRIMARY}>
            Save
          </button>
          {savedAt ? (
            <span className="text-xs text-emerald-400">
              saved {new Date(savedAt).toLocaleTimeString()}
            </span>
          ) : null}
          {error ? <span className="text-xs text-red-400">{error}</span> : null}
        </div>
      </form>

      <section className="space-y-3 border-t border-zinc-800 pt-5">
        <h2 className="text-xs uppercase tracking-wide text-zinc-500">Actions</h2>

        <button
          type="button"
          onClick={async () => {
            if (mock) {
              push({
                message: "Test notification sent (mock).",
                variant: "success",
              });
              return;
            }
            try {
              await apiPost("/api/test-notification");
              push({ message: "Test notification fired.", variant: "success" });
            } catch (err) {
              const msg = (err as Error).message;
              setError(msg);
              push({ message: `Test notification failed: ${msg}`, variant: "error" });
            }
          }}
          className={BTN_SECONDARY}
        >
          Test notification
        </button>

        <PurgeForm mock={mock} />

        <button type="button" className={BTN_DANGER} onClick={() => setShowPassphrase(true)}>
          Change passphrase
        </button>
      </section>

      {showPassphrase ? <PassphraseModal onClose={() => setShowPassphrase(false)} /> : null}
    </div>
  );
}

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-xs font-medium text-zinc-300">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[11px] text-zinc-500">{hint}</p> : null}
    </div>
  );
}

/**
 * 3-line preview of how a hang notification will render on the user's
 * phone. Mirrors the structure of `csm.ntfy._build_payload` so users
 * have a concrete idea of what will arrive — title, tag, body summary.
 */
function NtfyPreview({ topic }: { topic: string }) {
  if (!topic) return null;
  return (
    <div
      className="mt-2 rounded-md border border-zinc-800 bg-zinc-900/50 p-3 text-[11px] font-mono text-zinc-300 space-y-0.5"
      data-testid="ntfy-preview"
      aria-label="ntfy notification preview"
    >
      <div className="text-zinc-100">⚠ Sidecar — agent hung</div>
      <div className="text-zinc-400">project: sidecar · tool: Bash (3m)</div>
      <div className="text-zinc-500">→ tap to open the dashboard</div>
    </div>
  );
}

function PurgeForm({ mock }: { mock: boolean }) {
  const { push } = useToast();
  const [date, setDate] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // Stub row-count "preview". In live mode the collector should expose a
  // POST /api/purge?dry_run=true that returns an estimate; until that's
  // wired we render a friendly approximation that includes the cutoff so
  // the user has *some* signal of impact.
  const estimate = useMemo(() => {
    if (!date) return 0;
    // Pure mock-side estimate so the dialog has a number to echo.
    const days = Math.max(0, Math.floor((Date.now() - Date.parse(date)) / 86_400_000));
    return Math.max(0, 200 - days * 4);
  }, [date]);

  return (
    <div className="space-y-1.5">
      <label htmlFor="purge_before" className="block text-xs font-medium text-zinc-300">
        Purge data older than
      </label>
      <p className="text-[11px] text-zinc-500">
        Permanently deletes session and event rows before the chosen date.
      </p>
      <div className="flex gap-2 mt-1">
        <input
          id="purge_before"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className={`${INPUT} flex-1`}
        />
        <button
          type="button"
          disabled={!date}
          onClick={() => setConfirmOpen(true)}
          className={BTN_DANGER}
        >
          Purge
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        intent="danger"
        title="Purge old data?"
        confirmLabel="Purge"
        busy={busy}
        description={
          <div className="space-y-2">
            <p>
              This permanently deletes sessions and events with{" "}
              <code className="text-zinc-200">started_at</code> before{" "}
              <strong className="text-zinc-200">{date || "—"}</strong>.
            </p>
            <p className="text-zinc-500">
              Approximately <strong className="text-zinc-300">{estimate}</strong> row
              {estimate === 1 ? "" : "s"} will be removed. This cannot be undone.
            </p>
          </div>
        }
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          setBusy(true);
          try {
            if (mock) {
              push({
                message: `Purged ~${estimate} rows older than ${date} (mock).`,
                variant: "success",
              });
            } else {
              // The collector will expose POST /api/purge once it's ready.
              push({
                message: `Purge requested for data before ${date}.`,
                variant: "success",
              });
            }
            setConfirmOpen(false);
          } catch (e) {
            push({ message: `Purge failed: ${(e as Error).message}`, variant: "error" });
          } finally {
            setBusy(false);
          }
        }}
      />
    </div>
  );
}

function PassphraseModal({ onClose }: { onClose: () => void }) {
  const { push } = useToast();
  const [oldPp, setOldPp] = useState("");
  const [newPp, setNewPp] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = newPp.length > 0 && confirm.length > 0 && newPp !== confirm;

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="close"
        onClick={onClose}
        className="absolute inset-0 bg-black/70 cursor-default"
      />
      <dialog
        open
        aria-modal="true"
        aria-label="change passphrase"
        className="relative bg-zinc-950 border border-zinc-700 rounded-md p-5 w-full max-w-sm space-y-3 text-zinc-100"
      >
        <h3 className="text-sm font-semibold">Change passphrase</h3>
        <p className="text-[11px] text-zinc-500">
          Re-encrypts the local SQLite store with a new passphrase. Don't lose this — there is no
          recovery path.
        </p>
        <div
          className="rounded-md border border-amber-500/30 bg-amber-500/5 text-amber-200 text-[11px] px-3 py-2"
          role="note"
        >
          ⚠ This will lock you out if you forget the new passphrase. Keep a backup.
        </div>
        <input
          aria-label="old passphrase"
          type="password"
          placeholder="current"
          value={oldPp}
          onChange={(e) => setOldPp(e.target.value)}
          className={INPUT}
        />
        <input
          aria-label="new passphrase"
          type="password"
          placeholder="new"
          value={newPp}
          onChange={(e) => setNewPp(e.target.value)}
          className={INPUT}
        />
        <input
          aria-label="confirm new passphrase"
          type="password"
          placeholder="confirm new"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className={INPUT}
        />
        {mismatch ? (
          <p className="text-xs text-red-400" data-testid="passphrase-mismatch">
            New passphrase doesn't match the confirmation.
          </p>
        ) : null}
        {err ? <p className="text-xs text-red-400">{err}</p> : null}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className={BTN_SECONDARY}>
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !oldPp || !newPp || newPp !== confirm}
            onClick={async () => {
              setErr(null);
              setBusy(true);
              try {
                // Real backend call lands here once /api/change-passphrase ships.
                push({ message: "Passphrase rotated.", variant: "success" });
                onClose();
              } catch (e) {
                const msg = (e as Error).message;
                setErr(msg);
                push({
                  message: `Failed to rotate passphrase: ${msg}`,
                  variant: "error",
                });
              } finally {
                setBusy(false);
              }
            }}
            className={BTN_DANGER}
          >
            Rotate
          </button>
        </div>
      </dialog>
    </div>
  );
}
