import { type ReactNode, useEffect, useRef } from "react";

/**
 * Lightweight confirmation modal.
 *
 * Used for destructive actions (purge, passphrase rotate). Renders an
 * accessible <dialog>, traps focus on the cancel button on open so a stray
 * Enter doesn't accidentally confirm, and dismisses on Escape or backdrop
 * click.
 *
 * Visual: the title sets the question, the description echoes the relevant
 * specifics (cutoff date, row count, etc.), and the confirm CTA uses
 * `intent`-driven classes — `danger` for irreversible, `primary` for benign.
 */

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  /** Confirm button label. Defaults to "Confirm". */
  confirmLabel?: string;
  cancelLabel?: string;
  intent?: "danger" | "primary";
  busy?: boolean;
  onConfirm(): void;
  onCancel(): void;
}

const BTN_PRIMARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium bg-emerald-500 text-emerald-950 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_DANGER =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium text-red-200 bg-red-500/15 border border-red-500/60 hover:bg-red-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_SECONDARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm text-zinc-200 border border-zinc-700 hover:bg-zinc-800/80 disabled:opacity-50 transition-colors";

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  intent = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  // Focus the cancel button on open — safer default than confirm.
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);

  // Escape closes the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const confirmClass = intent === "danger" ? BTN_DANGER : BTN_PRIMARY;

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center p-4"
      role="presentation"
      data-testid="confirm-dialog"
    >
      <button
        type="button"
        aria-label="close"
        onClick={onCancel}
        className="absolute inset-0 bg-black/70 cursor-default"
      />
      <dialog
        open
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative bg-zinc-950 border border-zinc-700 rounded-md p-5 w-full max-w-sm text-zinc-100 space-y-3"
      >
        <h3 id="confirm-dialog-title" className="text-sm font-semibold">
          {title}
        </h3>
        {description ? <div className="text-[12px] text-zinc-400">{description}</div> : null}
        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            ref={cancelRef}
            onClick={onCancel}
            disabled={busy}
            className={BTN_SECONDARY}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={confirmClass}
            data-testid="confirm-dialog-confirm"
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </dialog>
    </div>
  );
}
