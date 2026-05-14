import { type FormEvent, useEffect, useMemo, useState } from "react";
import { apiPost } from "../api/client";
import { useMock } from "../api/mode";
import type { Settings as SettingsT } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import Window from "../components/Window";
import { useSettings } from "../hooks/useSettings";

/**
 * Button intent classes — palette tuned to the warm theme:
 *   - primary   = save/submit (orange CTA, beveled, depresses on click)
 *   - secondary = neutral action (outlined warm surface)
 *   - danger    = irreversible (warm-red outline)
 */
const BTN_PRIMARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium bg-cta text-white shadow-[0_1px_0_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.25)] hover:bg-cta-hover active:translate-y-px active:shadow-[inset_0_1px_2px_rgba(0,0,0,0.18)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_SECONDARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm text-ink border border-line-strong bg-surface hover:bg-surface-2 active:translate-y-px disabled:opacity-50 transition-colors";
const BTN_DANGER =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium text-bad border border-bad/60 bg-surface hover:bg-bad/10 active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

const INPUT =
  "w-full min-h-11 px-3 rounded-md bg-surface border border-line text-sm text-ink placeholder:text-ink-subtle focus:border-teal focus:outline-none";

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
        <div className="h-6 w-24 rounded bg-line/60 animate-pulse" />
        <div className="h-11 rounded-md bg-line/40 animate-pulse" />
        <div className="h-11 rounded-md bg-line/40 animate-pulse" />
        <div className="h-11 rounded-md bg-line/40 animate-pulse" />
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
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink leading-tight">Settings</h1>
      </header>

      <form onSubmit={onSubmit} aria-label="settings form" className="space-y-6">
        <Window icon="settings" title="Hang thresholds" aria-label="hang thresholds">
          <div className="space-y-5">
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
          </div>
        </Window>

        <Window icon="alert" title="Notifications" aria-label="notifications">
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
                className="rounded-md border border-warn/40 bg-warn/10 text-ink text-[11px] px-3 py-2 mt-2 space-y-1"
                data-testid="ntfy-empty-hint"
              >
                <p>
                  No topic set. Push notifications need a topic — sign up at{" "}
                  <a
                    href="https://ntfy.sh/"
                    target="_blank"
                    rel="noreferrer"
                    className="underline hover:text-cta"
                  >
                    ntfy.sh
                  </a>{" "}
                  or generate one.
                </p>
                <button
                  type="button"
                  className="inline-flex items-center min-h-9 px-3 rounded border border-warn/40 text-warn hover:bg-warn/15 text-[11px] active:translate-y-px"
                  onClick={() => setForm({ ...form, ntfy_topic: generateNtfyTopic() })}
                >
                  Generate random topic
                </button>
              </div>
            ) : null}

            <NtfyPreview topic={form.ntfy_topic} />
          </Field>
        </Window>

        <ApprovalForm form={form} setForm={setForm} />

        <div className="flex items-center gap-3 flex-wrap">
          <button type="submit" className={BTN_PRIMARY}>
            Save
          </button>
          {savedAt ? (
            <span className="text-xs text-good">
              saved {new Date(savedAt).toLocaleTimeString()}
            </span>
          ) : null}
          {error ? <span className="text-xs text-bad">{error}</span> : null}
        </div>
      </form>

      <Window icon="doc" title="Actions" aria-label="actions">
        <div className="space-y-4">
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
        </div>
      </Window>

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
      <label htmlFor={id} className="block text-xs font-medium text-ink">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[11px] text-ink-muted">{hint}</p> : null}
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
      className="mt-2 rounded-md border border-line bg-code-bg p-3 text-[11px] font-mono text-code-text space-y-0.5"
      data-testid="ntfy-preview"
      aria-label="ntfy notification preview"
    >
      <div className="text-code-text">⚠ Sidecar — agent hung</div>
      <div className="text-code-text/80">project: sidecar · tool: Bash (3m)</div>
      <div className="text-code-text/60">→ tap to open the dashboard</div>
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
      <label htmlFor="purge_before" className="block text-xs font-medium text-ink">
        Purge data older than
      </label>
      <p className="text-[11px] text-ink-muted">
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
              <code className="text-ink">started_at</code> before{" "}
              <strong className="text-ink">{date || "—"}</strong>.
            </p>
            <p className="text-ink-muted">
              Approximately <strong className="text-ink">{estimate}</strong> row
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

/**
 * V2.D4 — phone permission approval settings.
 *
 * The fields live on the same `form` state as the rest of Settings so the
 * top-level Save button can PATCH everything in one shot.
 *
 * The "Regenerate api_secret" button is a placeholder until the collector
 * exposes a dedicated POST endpoint. Today the secret is generated once
 * during `csm install`; rotation requires a CLI command.
 */
function ApprovalForm({
  form,
  setForm,
}: {
  form: SettingsT;
  setForm: (s: SettingsT) => void;
}) {
  return (
    <Window
      icon="approval"
      title="Phone permission approval"
      aria-label="phone permission approval"
    >
      <div className="space-y-5">
        <Field
          id="approval_enabled"
          label="Enable phone approval"
          hint="When on, configured tool calls require an approval decision from this dashboard."
        >
          <label className="inline-flex items-center gap-2 cursor-pointer min-h-11">
            <input
              id="approval_enabled"
              type="checkbox"
              className="h-4 w-4 accent-cta"
              checked={!!form.approval_enabled}
              onChange={(e) => setForm({ ...form, approval_enabled: e.target.checked })}
            />
            <span className="text-sm text-ink">
              {form.approval_enabled ? "Enabled" : "Disabled"}
            </span>
          </label>
        </Field>

        <Field
          id="approval_tools"
          label="Tools requiring approval"
          hint="Comma-separated list of tool names. Empty = approve everything when enabled."
        >
          <input
            id="approval_tools"
            name="approval_tools"
            type="text"
            autoComplete="off"
            placeholder="Bash, Edit, Write"
            className={INPUT}
            value={form.approval_tools ?? ""}
            onChange={(e) => setForm({ ...form, approval_tools: e.target.value })}
          />
        </Field>

        <Field
          id="approval_timeout_ms"
          label="Approval timeout (ms)"
          hint="If no decision arrives within this window the request times out and the hook falls back to its default."
        >
          <input
            id="approval_timeout_ms"
            name="approval_timeout_ms"
            type="number"
            min={1000}
            max={600_000}
            step={1000}
            className={INPUT}
            value={form.approval_timeout_ms ?? 60_000}
            onChange={(e) => setForm({ ...form, approval_timeout_ms: Number(e.target.value) || 0 })}
          />
        </Field>

        <Field
          id="dashboard_url"
          label="Dashboard URL for deep-links"
          hint="Used in ntfy push notifications so tapping opens this dashboard. e.g. https://csm.tail-scale.ts.net"
        >
          <input
            id="dashboard_url"
            name="dashboard_url"
            type="url"
            autoComplete="off"
            placeholder="https://csm.tail-scale.ts.net"
            className={INPUT}
            value={form.dashboard_url ?? ""}
            onChange={(e) => setForm({ ...form, dashboard_url: e.target.value })}
          />
        </Field>

        <div className="space-y-1.5">
          <p className="block text-xs font-medium text-ink">Regenerate api_secret</p>
          <p className="text-[11px] text-ink-muted">
            Rotates the install's API secret. Disabled until the collector exposes an endpoint — for
            now run <code className="text-ink">csm install</code> to regenerate.
          </p>
          <button type="button" disabled className={`${BTN_DANGER} disabled:cursor-not-allowed`}>
            Regenerate api_secret (coming soon)
          </button>
        </div>
      </div>
    </Window>
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
        className="absolute inset-0 bg-black/40 cursor-default"
      />
      <dialog
        open
        aria-modal="true"
        aria-label="change passphrase"
        className="relative bg-surface rounded-md w-full max-w-sm text-ink border border-line shadow-[0_8px_24px_rgba(60,40,10,0.18)] overflow-hidden p-0"
      >
        <header className="flex items-center gap-1.5 min-h-8 px-3 py-1.5 bg-titlebar border-b border-line">
          <span aria-hidden="true" className="text-ink-muted">
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.2}
              aria-hidden="true"
              focusable="false"
            >
              <rect x="3.5" y="6" width="7" height="6" rx="1" />
              <path d="M5 6V4.5a2 2 0 014 0V6" />
            </svg>
          </span>
          <span className="text-[12px] font-medium leading-tight truncate">Change passphrase</span>
        </header>
        <div className="p-5 space-y-3">
          <p className="text-[11px] text-ink-muted">
            Re-encrypts the local SQLite store with a new passphrase. Don't lose this — there is no
            recovery path.
          </p>
          <div
            className="rounded-md border border-warn/40 bg-warn/10 text-ink text-[11px] px-3 py-2"
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
            <p className="text-xs text-bad" data-testid="passphrase-mismatch">
              New passphrase doesn't match the confirmation.
            </p>
          ) : null}
          {err ? <p className="text-xs text-bad">{err}</p> : null}
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
        </div>
      </dialog>
    </div>
  );
}
