import { useStream } from "../hooks/useStream";

/**
 * Header connection indicator.
 *
 * Visual: a 10px dot + always-visible lowercase label. Earlier the label hid
 * below `sm:` — that left a 2×2px dot at 380px wide which was both invisible
 * to screen readers (it's just an aria-label) and indistinguishable to
 * non-technical viewers. We now show "live" / "offline" inline at all
 * widths; the dot doubles as a colorblind-safe icon.
 *
 * `useStream()` is mounted once here; the underlying EventSource is shared.
 */
export default function ConnectionStatus() {
  const { status, lastEventAt } = useStream();

  const isPending = status === "reconnecting" || status === "connecting";
  const isLive = status === "connected";

  const dotColor = isLive ? "bg-emerald-500" : isPending ? "bg-amber-400" : "bg-red-500";
  const textColor = isLive ? "text-emerald-300" : isPending ? "text-amber-300" : "text-red-300";

  const label = isLive
    ? "live"
    : status === "reconnecting"
      ? "reconnecting"
      : status === "connecting"
        ? "connecting"
        : "offline";

  const tooltip = lastEventAt
    ? `${label} · last event ${new Date(lastEventAt).toLocaleTimeString()}`
    : `${label} · no events yet`;

  return (
    <output
      aria-label={`stream status: ${status}`}
      aria-live="polite"
      title={tooltip}
      className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${textColor}`}
    >
      <span
        aria-hidden="true"
        className={`inline-block w-2.5 h-2.5 rounded-full ${dotColor} ${
          isPending ? "animate-pulse" : ""
        }`}
      />
      <span>{label}</span>
    </output>
  );
}
