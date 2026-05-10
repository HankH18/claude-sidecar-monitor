import { useStream } from "../hooks/useStream";

/**
 * Header status dot. Green = SSE open, amber = reconnecting, red = closed.
 *
 * Mounts its own `useStream()` rather than threading through props — the
 * underlying EventSource is shared via the browser's HTTP layer; an extra
 * subscriber is cheap.
 */
export default function ConnectionStatus() {
  const { status, lastEventAt } = useStream();

  const color =
    status === "connected"
      ? "bg-emerald-500"
      : status === "reconnecting"
        ? "bg-amber-400"
        : status === "connecting"
          ? "bg-amber-400"
          : "bg-red-500";

  const label =
    status === "connected"
      ? "Live"
      : status === "reconnecting"
        ? "Reconnecting"
        : status === "connecting"
          ? "Connecting"
          : "Disconnected";

  const tooltip = lastEventAt
    ? `${label} · last event ${new Date(lastEventAt).toLocaleTimeString()}`
    : `${label} · no events yet`;

  return (
    <output
      aria-label={`stream status: ${status}`}
      aria-live="polite"
      title={tooltip}
      className="inline-flex items-center gap-1.5 text-[10px] text-zinc-500"
    >
      <span
        aria-hidden="true"
        className={`inline-block w-2 h-2 rounded-full ${color} ${
          status === "reconnecting" || status === "connecting" ? "animate-pulse" : ""
        }`}
      />
      <span className="hidden sm:inline">{label}</span>
    </output>
  );
}
