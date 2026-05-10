// Phase 7 (T16) fills this in. v0.1 scaffold renders a placeholder.

export default function Overview() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Live agents</h1>
        <p className="text-sm text-zinc-500 mt-1">No active sessions.</p>
      </div>
      <p className="text-xs text-zinc-600">
        This is a v0.1 scaffold. The Overview page lights up once the collector starts sending SSE
        events.
      </p>
    </div>
  );
}
