import { type ButtonHTMLAttributes, type ReactNode, forwardRef } from "react";

/**
 * Sidecar button — two variants matching the PostHog-inspired warm theme.
 *
 *   - "primary"   → orange CTA, subtle bevel + inset shadow, depresses on click
 *   - "secondary" → outlined surface card, depresses on click
 *   - "danger"    → outlined warm-red, for irreversible actions
 *   - "ghost"     → minimal, used inside tight rows / nested toolbars
 *
 * All variants share the ≥44pt tap target (min-h-11) and a sentence-case
 * text style. The "active:translate-y-px + inset shadow" combo gives the
 * signature "button depresses" feel.
 */

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /** Render with reduced vertical padding for tight rows (still ≥44pt). */
  compact?: boolean;
  children: ReactNode;
}

const BASE =
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors select-none disabled:opacity-50 disabled:cursor-not-allowed disabled:active:translate-y-0";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: [
    "bg-cta text-white",
    "shadow-[0_1px_0_rgba(0,0,0,0.15),inset_0_1px_0_rgba(255,255,255,0.25)]",
    "hover:bg-cta-hover",
    "active:translate-y-px active:shadow-[inset_0_1px_2px_rgba(0,0,0,0.18)]",
  ].join(" "),
  secondary: [
    "bg-surface text-ink border border-line-strong",
    "shadow-[0_1px_0_rgba(0,0,0,0.04)]",
    "hover:bg-surface-2",
    "active:translate-y-px active:shadow-[inset_0_1px_2px_rgba(0,0,0,0.08)]",
  ].join(" "),
  danger: [
    "bg-surface text-bad border border-bad/60",
    "hover:bg-bad/10",
    "active:translate-y-px",
  ].join(" "),
  ghost: ["bg-transparent text-ink-muted", "hover:bg-surface-2 hover:text-ink"].join(" "),
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", compact = false, className = "", type = "button", children, ...rest },
  ref,
) {
  const size = compact ? "min-h-9 px-3" : "min-h-11 px-4";
  return (
    <button
      ref={ref}
      type={type === "submit" || type === "reset" ? type : "button"}
      className={`${BASE} ${VARIANTS[variant]} ${size} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});

export default Button;
