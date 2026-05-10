import { type FormEvent, useEffect, useState } from "react";
import { apiPost } from "../api/client";
import { useMock } from "../api/mode";
import type { Settings as SettingsT } from "../api/types";
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

export default function Settings() {
  const { settings, loading, save } = useSettings();
  const mock = useMock();
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
    } catch (err) {
      setError((err as Error).message);
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
              // Mock just logs.
              console.log("[mock] test notification fired");
              return;
            }
            try {
              await apiPost("/api/test-notification");
            } catch (err) {
              setError((err as Error).message);
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

function PurgeForm({ mock }: { mock: boolean }) {
  const [date, setDate] = useState("");
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
          onClick={() => {
            if (mock) {
              console.log(`[mock] purge data older than ${date}`);
              return;
            }
            // The collector will expose POST /api/purge once it's ready.
            console.log("purge", date);
          }}
          className={BTN_DANGER}
        >
          Purge
        </button>
      </div>
    </div>
  );
}

function PassphraseModal({ onClose }: { onClose: () => void }) {
  const [oldPp, setOldPp] = useState("");
  const [newPp, setNewPp] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
                console.log("[mock] rotate passphrase");
                onClose();
              } catch (e) {
                setErr((e as Error).message);
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
