import { type FormEvent, useEffect, useState } from "react";
import { apiPost } from "../api/client";
import { useMock } from "../api/mode";
import type { Settings as SettingsT } from "../api/types";
import { useSettings } from "../hooks/useSettings";

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
    return <div className="h-32 rounded-md bg-zinc-900/60 animate-pulse" aria-busy="true" />;
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
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
      </header>

      <form onSubmit={onSubmit} className="space-y-4" aria-label="settings form">
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
            className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
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
            className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
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
            className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
            value={form.ntfy_topic}
            onChange={(e) => setForm({ ...form, ntfy_topic: e.target.value })}
          />
        </Field>

        <div className="flex items-center gap-2">
          <button
            type="submit"
            className="px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-sm hover:bg-emerald-500/30"
          >
            Save
          </button>
          {savedAt ? (
            <span className="text-xs text-zinc-500">
              saved {new Date(savedAt).toLocaleTimeString()}
            </span>
          ) : null}
          {error ? <span className="text-xs text-red-400">{error}</span> : null}
        </div>
      </form>

      <section className="space-y-3 border-t border-zinc-900 pt-4">
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
          className="px-3 py-1.5 rounded border border-zinc-800 text-sm text-zinc-200 hover:bg-zinc-900"
        >
          Test notification
        </button>

        <PurgeForm mock={mock} />

        <button
          type="button"
          className="px-3 py-1.5 rounded border border-zinc-800 text-sm text-zinc-200 hover:bg-zinc-900"
          onClick={() => setShowPassphrase(true)}
        >
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
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-zinc-300">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[10px] text-zinc-600">{hint}</p> : null}
    </div>
  );
}

function PurgeForm({ mock }: { mock: boolean }) {
  const [date, setDate] = useState("");
  return (
    <div className="space-y-1">
      <label htmlFor="purge_before" className="block text-xs font-medium text-zinc-300">
        Purge data older than
      </label>
      <div className="flex gap-2">
        <input
          id="purge_before"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="flex-1 px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
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
          className="px-3 py-1.5 rounded border border-zinc-800 text-sm text-zinc-200 disabled:opacity-50 hover:bg-zinc-900"
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
        className="relative bg-zinc-950 border border-zinc-800 rounded-md p-4 w-full max-w-sm space-y-3 text-zinc-200"
      >
        <h3 className="text-sm font-semibold text-zinc-100">Change passphrase</h3>
        <input
          aria-label="old passphrase"
          type="password"
          placeholder="current"
          value={oldPp}
          onChange={(e) => setOldPp(e.target.value)}
          className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
        />
        <input
          aria-label="new passphrase"
          type="password"
          placeholder="new"
          value={newPp}
          onChange={(e) => setNewPp(e.target.value)}
          className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
        />
        <input
          aria-label="confirm new passphrase"
          type="password"
          placeholder="confirm new"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="w-full px-2 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
        />
        {err ? <p className="text-xs text-red-400">{err}</p> : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded border border-zinc-800 text-sm text-zinc-300 hover:bg-zinc-900"
          >
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
            className="px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-sm disabled:opacity-50"
          >
            Rotate
          </button>
        </div>
      </dialog>
    </div>
  );
}
