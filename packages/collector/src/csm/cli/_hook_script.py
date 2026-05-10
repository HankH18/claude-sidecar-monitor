"""Bundled shell script that Claude Code invokes for each hook event.

The script is installed at ``~/.csm/csm-hook.sh`` by ``csm install-hooks``.
It receives a JSON payload on stdin (the Claude Code hook payload) and POSTs
it to the local collector at ``http://127.0.0.1:8765/hook/<event_name>``.

Keeping the script content here as a string constant means it ships inside
the wheel — no separate template file to ship, and tests can import the
constant directly. The script intentionally has zero non-stdlib dependencies
beyond ``curl`` (universally available on macOS).

The collector — not the shell script — is the source of truth for hook
timestamps. macOS BSD ``date`` doesn't support ``%3N`` (millis), so the
script doesn't try to produce one.
"""

from __future__ import annotations

# NOTE: Do NOT add `set -e` — if curl fails (collector is down) we still want
# the hook to exit 0 so Claude Code keeps running. Failure is logged via the
# `--max-time` exit code being silently ignored.
HOOK_SCRIPT = """\
#!/bin/sh
# claude-sidecar-monitor hook bridge.
# Installed by `csm install-hooks`. Do not edit by hand — re-run installer.
#
# Receives a JSON Claude Code hook payload on stdin and POSTs it to the
# local csm collector. Falls back silently if the collector is down so a
# stopped collector never blocks Claude Code itself.

EVENT_NAME="${1:-unknown}"
URL="http://127.0.0.1:8765/hook/${EVENT_NAME}"

# `cat -` reads stdin into memory; hook payloads are small (<<64 KiB).
PAYLOAD="$(cat -)"

# `--max-time 2` keeps Claude Code responsive even if the collector hangs.
# `-s` silences progress, `-o /dev/null` discards the (always `{}`) response.
# We deliberately don't `set -e` — a failed POST must not break Claude Code.
curl -s -o /dev/null \\
    --max-time 2 \\
    -H "Content-Type: application/json" \\
    -X POST \\
    --data "${PAYLOAD}" \\
    "${URL}" || true

exit 0
"""
