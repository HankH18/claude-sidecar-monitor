import { useStream } from "../hooks/useStream";

/**
 * Header connection indicator.
 *
 * Visual: a 10px dot + always-visible lowercase label. The pulsing dot is
 * driven by `animate-pulse` for transient (connecting/reconnecting) states.
 * Colors come from the warm-state palette so the indicator reads as part
 * of the PostHog-inspired theme rather than the previous neon-on-black look.
 */
export default function ConnectionStatus() {
  const { status, lastEventAt } = useStream();

  const isPending = status === "reconnecting" || status === "connecting";
  const isLive = status === "connected";

  const dotColor = isLive ? "bg-good" : isPending ? "bg-warn" : "bg-bad";
  const textColor = isLive ? "text-good" : isPending ? "text-warn" : "text-bad";

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
          isPending || isLive ? "animate-pulse" : ""
        }`}
      />
      <span>{label}</span>
    </output>
  );
}
