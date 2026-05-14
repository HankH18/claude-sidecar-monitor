import { type ReactNode, useEffect, useRef } from "react";

/**
 * Lightweight confirmation modal — rendered with the same window chrome
 * the rest of the dashboard uses, so destructive prompts feel like a real
 * "this is a separate decision" surface.
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
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium bg-cta text-white shadow-[0_1px_0_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.25)] hover:bg-cta-hover active:translate-y-px active:shadow-[inset_0_1px_2px_rgba(0,0,0,0.18)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_DANGER =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm font-medium text-bad bg-surface border border-bad/60 hover:bg-bad/10 active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed transition-colors";
const BTN_SECONDARY =
  "inline-flex items-center justify-center min-h-11 px-4 rounded-md text-sm text-ink border border-line-strong bg-surface hover:bg-surface-2 active:translate-y-px disabled:opacity-50 transition-colors";

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
        className="absolute inset-0 bg-black/40 cursor-default"
      />
      <dialog
        open
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative bg-surface rounded-md w-full max-w-sm text-ink border border-line shadow-[0_8px_24px_rgba(60,40,10,0.18)] overflow-hidden p-0"
      >
        <header className="flex items-center gap-1.5 min-h-8 px-3 py-1.5 bg-titlebar border-b border-line">
          <span aria-hidden="true" className="text-ink-muted">
            {intent === "danger" ? (
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
                <path d="M7 2l5.2 9.5H1.8L7 2z" />
                <path d="M7 6v3" strokeLinecap="round" />
                <circle cx="7" cy="10.2" r="0.6" fill="currentColor" stroke="none" />
              </svg>
            ) : (
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
                <circle cx="7" cy="7" r="5.5" />
                <path d="M7 4.5v3" strokeLinecap="round" />
                <circle cx="7" cy="9.6" r="0.55" fill="currentColor" stroke="none" />
              </svg>
            )}
          </span>
          <h3 id="confirm-dialog-title" className="text-[12px] font-medium leading-tight truncate">
            {title}
          </h3>
        </header>
        <div className="p-4 space-y-3">
          {description ? <div className="text-xs text-ink-muted">{description}</div> : null}
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
        </div>
      </dialog>
    </div>
  );
}
