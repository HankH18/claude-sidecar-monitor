# claude-sidecar-monitor — Build Spec

Canonical build specification for `claude-sidecar-monitor` v0.1.0. Authored 2026-05-10 to consolidate decisions made during the Intent-era planning phase plus best-practice updates negotiated at the Claude Code handoff.

This document supersedes the Intent-era spec note. It is self-contained — no external references to "§3 of the build spec" or similar are needed.

---

## 1. Goal

Ship v0.1.0 of `claude-sidecar-monitor` (`csm`): a macOS-resident, mobile-PWA observability dashboard for Claude Code agent sessions. From a phone, answer three glance-questions:

1. What agents are running right now?
2. Are any of them hung?
3. Where are tokens going (per agent / per project)?

Plus: render the agent tree, store full transcripts for after-the-fact debugging, push ntfy notifications on hang/done.

### Why

The user runs Claude Code agents (often spawned by Augment Intent under BYOA configuration) on his Mac. Long-running agents are a black box once he walks away from the keyboard. This is the phone-glance dashboard he wishes existed.

---

## 2. Locked decisions

| Concern | Decision | Notes |
|---|---|---|
| Backend language | **Python 3.12 + FastAPI**, managed with `uv` | ADR-001 |
| Backend distribution | **`uv tool install`** (PyPI publish for v0.2; local install via `uv tool install ./packages/collector` for v0.1) | ADR-003 — replaces PyInstaller |
| Frontend | **React 18 + Vite + TypeScript + Tailwind**, PWA, `react-arborist` for tree | |
| Storage | **SQLCipher** via `pysqlcipher3` against Homebrew `sqlcipher` | ADR-002 — replaces `sqlcipher3-binary` PyPI wheel |
| DB path | `~/Library/Application Support/claude-sidecar-monitor/store.db` | Override via `CSM_DB_PATH` |
| Encryption | **Argon2id** KDF, key in **macOS Keychain** | `time_cost=3, memory_cost=64MB, parallelism=4`, hash 32 bytes |
| Listener | `127.0.0.1:8765` | |
| Distribution | launchd LaunchAgent + Tailscale Serve | User-level, not root |
| Notifications | ntfy.sh (public) | Topic stored in `settings`; empty topic = no-op |
| Logs | `~/Library/Logs/claude-sidecar-monitor/` | |
| License | MIT | Public repo `claude-sidecar-monitor` |
| Commits | Conventional Commits, Husky + commitlint enforced | |

### Terminology

The Intent-era spec used "Space" for a worktree-grouped agent session. **This spec uses "Project"** to match Claude Code's data model. A *Project* is a directory tree (resolved by walking up to the nearest `.git`). Multiple *Sessions* may exist in one Project. *Subagent sessions* are children of a parent session, spawned via the `Task` tool.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  macOS host                                                          │
│                                                                      │
│  shell / Intent / IDE ──spawns──▶ claude (Claude Code CLI)           │
│                                │                                     │
│                  hook POSTs    │   JSONL writes                      │
│                                ▼                                     │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Collector (launchd-managed FastAPI server, port 8765)          │  │
│  │  • POST /hook/<event>          ← Claude Code hooks             │  │
│  │  • watchdog ~/.claude/projects ← JSONL ingestion               │  │
│  │  • Hang scanner (asyncio loop, 5 s cadence)                    │  │
│  │  • Token aggregator (per-session + subtree rollup)             │  │
│  │  • Agent tree builder                                          │  │
│  │  • SQLCipher store at ~/Library/Application Support/csm/       │  │
│  │  • SSE /stream  +  GET /api/* JSON                             │  │
│  │  • ntfy.sh dispatcher                                          │  │
│  │  • Static React PWA at /                                       │  │
│  └────────────────────┬───────────────────────────────────────────┘  │
│                       │ Tailscale Serve (tailnet-only HTTPS)         │
└───────────────────────┼─────────────────────────────────────────────┘
                        ▼
                📱 iPhone Safari → Add to Home Screen
                React PWA: agents · tree · sessions · tokens · settings
```

### Sequence: hook arrives → UI updates

1. `claude` fires a hook. The script `~/.claude/hooks/csm-hook.sh` POSTs the JSON payload to `http://127.0.0.1:8765/hook/<event>`.
2. Receiver (T6) validates event name, server-side-timestamps it, appends to `events` table, applies a state-machine transition on the `sessions` row, and emits to the in-process bus.
3. The token aggregator (T9) — already subscribed to the bus — recomputes denormalized totals on the affected `sessions` row when triggered by a `transcript_message` ingest from T7 (debounced ≤1/2s/session).
4. The SSE multiplexer (T11) receives bus events and pushes them to connected dashboards as `session_update`, `event`, `transcript_message`, `hang`, or `settings_changed`.
5. The dashboard, holding an `EventSource` connection to `/stream`, updates the affected component without a refetch.

### Two ingestion sources, deliberately

- **Hooks** — low-latency state machine driver. The receiver gets state transitions in <1 s.
- **JSONL** — authoritative source for token usage, prompt/response content, and tool I/O. Hooks don't carry the full message body.

Both are needed. Hooks alone miss token data; JSONL alone is too lagged for live state.

---

## 4. Data model

### 4.1 State machine

A session moves through:

```
       SessionStart
  ─────────────────▶  running
                       │  ▲
            PreToolUse │  │ PostToolUse
                       ▼  │
                       tool
                       │  ▲
                       │  │ (any event arrives)
                       ▼  │
                       hung  ◀──── scanner: now - last_event_at > red_threshold_ms
                       │
                       │ Notification(permission_request)
                       ▼
                     waiting_user
                       │
                       │ (next event)
                       ▼
                     running …
                       │
            Stop / SessionEnd / SubagentStop
                       ▼
                       done
```

Transitions on each hook event:

| Hook event              | From state             | To state         | Notes |
|-------------------------|------------------------|------------------|-------|
| `SessionStart`          | (none / `done`)         | `running`        | Creates row, captures `worktree_root`, `cwd`. `source` field = `startup`/`resume`/`clear`/`compact` |
| `UserPromptSubmit`      | `running`/`tool`/`waiting_user` | `running` | bumps `last_event_at` |
| `PreToolUse`            | `running`               | `tool`           | sets `last_tool_name`. If `tool_name == "Task"`, queue tree match |
| `PostToolUse`           | `tool`                  | `running`        | clears `last_tool_name`, records `duration_ms` |
| `Notification`          | any → matching          | `waiting_user` (if `notification_type == "permission_request"`); else no change | triggers ntfy `waiting_user` |
| `PreCompact`            | any                     | unchanged        | sets `last_event_name`; scanner extends thresholds by 60 s |
| `SessionEnd`            | any                     | `done`           | top-level only triggers ntfy `complete` |
| `Stop`                  | any                     | `done`           | same |
| `SubagentStop`          | any                     | `done`           | child only |
| `Setup`                 | any                     | unchanged        | informational |
| `PermissionRequest`     | any                     | `waiting_user`   | future v2 hook (architecture-ready) |
| (scanner)               | `running`/`tool`        | `hung`           | when `now - last_event_at > red_threshold_ms` |

Unknown events: log + reject with HTTP 400.

### 4.2 SQLite schema

Migration `001_init.sql`:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE sessions (
    session_id           TEXT PRIMARY KEY,
    parent_session_id    TEXT,
    worktree_root        TEXT NOT NULL,
    project_label        TEXT,
    cwd                  TEXT NOT NULL,
    transcript_path      TEXT,
    agent_type           TEXT,           -- 'coordinator' | 'implementor' | 'verifier' | 'subagent' | 'unknown'
    state                TEXT NOT NULL DEFAULT 'running',
    last_event_at        TEXT NOT NULL,  -- ISO 8601 UTC
    last_event_name      TEXT,
    last_tool_name       TEXT,
    started_at           TEXT NOT NULL,
    completed_at         TEXT,
    primary_model        TEXT,
    -- denormalized token totals (T9 maintains these)
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens   INTEGER NOT NULL DEFAULT 0,
    -- v2 hook-receiver readiness
    notification         TEXT,           -- JSON; per-session overrides
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
);

CREATE INDEX idx_sessions_worktree     ON sessions(worktree_root);
CREATE INDEX idx_sessions_parent       ON sessions(parent_session_id);
CREATE INDEX idx_sessions_state        ON sessions(state);
CREATE INDEX idx_sessions_last_event   ON sessions(last_event_at);
CREATE INDEX idx_sessions_started_at   ON sessions(started_at);

CREATE TABLE events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    event_name    TEXT NOT NULL,
    received_at   TEXT NOT NULL,         -- server-side timestamp (ISO 8601 UTC)
    tool_name     TEXT,
    tool_use_id   TEXT,
    duration_ms   INTEGER,
    payload_json  TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_events_session  ON events(session_id, received_at DESC);
CREATE INDEX idx_events_name     ON events(event_name, received_at DESC);

CREATE TABLE transcript_messages (
    message_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                    TEXT NOT NULL,
    role                          TEXT NOT NULL,         -- 'user' | 'assistant' | 'system' | 'tool_result'
    timestamp                     TEXT NOT NULL,
    content_json                  TEXT NOT NULL,         -- full JSONL message preserved
    model                         TEXT,
    input_tokens                  INTEGER,
    output_tokens                 INTEGER,
    cache_creation_input_tokens   INTEGER,
    cache_read_input_tokens       INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_transcript_session  ON transcript_messages(session_id, timestamp);
CREATE INDEX idx_transcript_model    ON transcript_messages(model, timestamp);

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE _offsets (
    file_path    TEXT PRIMARY KEY,
    byte_offset  INTEGER NOT NULL,
    last_inode   INTEGER,
    last_seen    TEXT NOT NULL
);

-- Seed defaults (no plan_seat_type — out of scope)
INSERT INTO settings (key, value) VALUES
    ('hang_yellow_ms', '60000'),
    ('hang_red_ms',    '180000'),
    ('ntfy_topic',     '');
```

### 4.3 JSONL ingestion

Claude Code writes one JSONL file per session at:

```
~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl
```

(`<encoded-cwd>` is the cwd with `/` replaced by `-`, leading slash stripped.)

Each line is a JSON object. Relevant message types:
- `user` — user prompts.
- `assistant` — model responses; carry a `message.usage` block with `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, plus `message.model`.
- `tool_use` — embedded in assistant messages.
- `tool_result` — tool outputs.
- `summary` — periodic compaction summaries.

The watcher (T7):
1. On startup, scans `~/.claude/projects/` recursively, indexes existing files, retrieves last byte offset from `_offsets`.
2. Subscribes to FSEvents via `watchdog`.
3. On change, opens file, seeks to last offset, reads new lines, parses each JSON, persists to `transcript_messages`.
4. Updates `_offsets.byte_offset` after each successful batch.
5. On rotation (inode change), resets offset to 0 and re-reads.
6. Garbage lines (parse failure) are logged and skipped; ingestion continues.
7. Emits `transcript_message` to bus for each persisted row, debounced per-session at ≤1 token-aggregation trigger per 2 s.

### 4.4 Agent tree derivation

Heuristic, applied on every `Task`-tool `PreToolUse` and on every fresh session start:

1. **Worktree grouping** — sessions with the same `worktree_root` form a Project group.
2. **Task-tool edge** — when parent P emits `PreToolUse(tool_name="Task")`, queue an open match window for P (30 s).
3. **First-event match** — a child session whose first hook event arrives within the parent's match window AND shares `worktree_root` is bound: `child.parent_session_id = P.session_id`.
4. **Fallback** — children that don't match a Task call appear at the Project root level (orphans).

Resolved `parent_session_id` is persisted on the child's `sessions` row. Tree queries walk upward from each session.

---

## 5. Hook receiver shape

### Endpoint

`POST /hook/<event>` where `<event>` is one of: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Notification`, `Stop`, `SubagentStop`, `SessionEnd`, `PreCompact`, `Setup`, `PermissionRequest`. Unknown events return 400.

### Request body

The full Claude Code hook payload, JSON. Fields used:
- `session_id` (UUID, required)
- `transcript_path` (path to JSONL, present on most events)
- `cwd` (working directory, present on `SessionStart`)
- `permission_mode` (string)
- `hook_event_name` (mirrors path segment; ignored)
- `tool_name`, `tool_input`, `tool_response` (Pre/PostToolUse)
- `tool_use_id` (Pre/PostToolUse)
- `source` (`SessionStart` only; `startup`/`resume`/`clear`/`compact`)
- `last_assistant_message` (`Stop`)
- `notification_type` (`Notification`; e.g., `permission_request`)

### Response

```json
{}
```

The server returns `200 {}` always in v0.1. The response shape is the v2-ready
`PreToolUse` decision shape — future versions can return:

```json
{
  "permissionDecision": "allow" | "deny" | "ask",
  "permissionDecisionReason": "..."
}
```

without changing the contract. v0.1 always returns `{}` (no-op).

### Behavior

- Server-side timestamp (`received_at = datetime.utcnow()`).
- The shell hook script must NOT be the timestamp source — `date +%3N` is GNU-only and macOS BSD `date` produces garbage.
- All transitions per the §4.1 table.
- Rejected events: 400 with `{"error": {"code": "unknown_event", "message": "..."}}`.
- Latency budget: respond within 5 s. Heavy work (token aggregation, tree rebuild) happens off the request path via the in-process bus.

---

## 6. Components & modules

```
packages/collector/src/csm/
├── __init__.py             # __version__ = "0.1.0"
├── server.py               # FastAPI app, lifespan, route mount
├── config.py               # paths, env-var overrides, settings dataclass
├── bus.py                  # asyncio in-process pub/sub for ingest events
├── db/
│   ├── __init__.py         # connect(key=None), connection pool
│   ├── migrations/
│   │   └── 001_init.sql
│   └── runner.py           # idempotent migration runner
├── crypto/
│   ├── __init__.py         # derive_key, get_key_from_keychain, store_key, rotate
│   └── BENCH.md            # encryption overhead benchmark
├── hooks/
│   ├── __init__.py         # router
│   ├── receiver.py         # POST /hook/<event>
│   ├── state_machine.py    # transition function
│   └── worktree.py         # cwd → worktree_root
├── jsonl/
│   ├── __init__.py
│   ├── watcher.py          # FSEvents observer
│   ├── parser.py           # ccusage-shaped parser (re-implemented)
│   └── offsets.py          # _offsets table I/O
├── scanner/
│   └── __init__.py         # 5 s asyncio loop, hang detection
├── tokens/
│   └── __init__.py         # aggregator, subtree rollup, by-model, daily totals
├── tree/
│   └── __init__.py         # parent_session_id resolution
├── ntfy/
│   └── __init__.py         # httpx.AsyncClient dispatcher
├── api/
│   ├── __init__.py         # router mount
│   ├── state.py            # /api/state
│   ├── sessions.py         # /api/sessions/*
│   ├── tree.py             # /api/tree
│   ├── tokens.py           # /api/tokens
│   ├── settings.py         # /api/settings
│   └── stream.py           # /stream SSE multiplexer
└── cli/
    ├── __init__.py         # Typer app + entrypoint
    ├── start.py            # csm start
    ├── install.py          # csm install (orchestrates the rest)
    ├── hooks.py            # csm install-hooks / csm hooks --dry-run
    ├── launchd.py          # csm install-launchd / uninstall
    ├── doctor.py           # csm doctor
    ├── purge.py            # csm purge
    ├── passphrase.py       # csm change-passphrase
    └── version.py          # csm version
```

```
packages/dashboard/src/
├── main.tsx                # Vite entrypoint
├── App.tsx                 # router shell + theme
├── index.css               # Tailwind
├── api/
│   ├── client.ts           # fetch wrapper, error handling
│   ├── stream.ts           # SSE client with auto-reconnect
│   └── types.ts            # API response types (mirror Pydantic)
├── hooks/
│   ├── useStream.ts        # subscribe to SSE topics
│   └── useSession.ts       # session detail hook
├── components/
│   ├── StatePill.tsx       # color + icon (a11y)
│   ├── TokenBadge.tsx      # input/output + cache secondary
│   ├── ElapsedClock.tsx    # 1 Hz client-side
│   ├── TreeNode.tsx        # react-arborist node renderer
│   └── DiffViewer.tsx      # tool I/O syntax-highlight
└── pages/
    ├── Overview.tsx        # /
    ├── ProjectDetail.tsx   # /projects/:encoded
    ├── SessionDetail.tsx   # /sessions/:id
    ├── Tokens.tsx          # /tokens
    └── Settings.tsx        # /settings
```

---

## 7. API contract (v0.1)

All endpoints under `/api/`. Static dashboard mounted at `/`. SSE at `/stream`.

### REST

- `GET /healthz` → `{"ok": true, "version": "0.1.0"}`
- `GET /api/state` → snapshot: `{sessions: Session[], settings: Settings, lastEventAt: string}`
- `GET /api/sessions/:id` → full session row + per-model token breakdown
- `GET /api/sessions/:id/transcript?cursor=&limit=` → cursor-paginated transcript messages
- `GET /api/tree?worktree=<root>` → nodes with own + subtree token totals
- `GET /api/tokens` → `{topSessions, topProjects, totalsByModel, dailyTotals}`
- `GET /api/settings` → settings JSON (no `plan_seat_type`)
- `PATCH /api/settings` → update settings
- `POST /api/test-notification` → fire a sample ntfy

Errors:

```json
{"error": {"code": "...", "message": "..."}}
```

### SSE

`GET /stream` (text/event-stream). Event shape:

```json
{
  "kind": "session_update" | "event" | "transcript_message" | "hang" | "settings_changed",
  "session_id": "...",
  "data": { ... }
}
```

`session_update` always carries the four token totals so the dashboard can update without a refetch.

---

## 8. Acceptance criteria (v0.1.0)

A release is acceptable when all of the following hold:

1. **Hooks fire.** A bare-shell `claude` invocation produces SessionStart/PreToolUse/PostToolUse/Stop on the receiver. (Verified via `csm doctor --gate-test`; result captured in `docs/gate-result.md`.)
2. **One-command install** in <5 min from `csm install`.
3. **Live agent list** within 2 s of session start.
4. **Hang detection** with yellow → red → ntfy push.
5. **Per-agent token totals.** Within 5 s of an assistant response, the affected session's `input/output/cache_read/cache_write` counts update. Tree shows per-node and subtree totals inline.
6. **Agent tree** renders parent/child for a multi-implementor Project.
7. **Conversation data** — full prompt-by-prompt transcript with diffs.
8. **Persistence** across collector restart; `csm doctor` clean.
9. **PWA** standalone, dark, custom icon on iPhone home screen.
10. **Polish** — README has hero, GIF, why, quickstart, diagram, troubleshooting; MIT; v0.1.0 tagged.
11. **At-rest encryption.** SQLite store opens only with the user's passphrase-derived key (cached in Keychain). `xxd store.db | head` shows random-looking bytes; `csm change-passphrase` rotates without data loss.

---

## 9. Non-goals (deferred to v2)

- **Remote permission approval.** Architecture leaves the door open: hook receiver uses the `permissionDecision`-capable response shape, returning `{}` in v0.1.
- Agent-team execution graphs.
- Retroactive cost analysis dashboard.
- Multi-Mac aggregation.
- Exportable session reports.
- Linear/GitHub integration.
- Plan-ceiling estimation, custom_max algorithm, seat multipliers, burn-rate projection. (Token math in v0.1 is per-session totals + subtree rollups; no projection.)

---

## 10. Risks & fragility

1. **`pysqlcipher3` build dependency.** Requires `brew install sqlcipher`. The README quickstart and `csm install` both check for it. Mitigation: a friendly error if missing.
2. **Anthropic-side JSONL format drift.** The token aggregator depends on `message.usage.{input_tokens,output_tokens,cache_creation_input_tokens,cache_read_input_tokens}`. Format changes will silently produce zero token totals. Mitigation: integration test against a captured sample, log warnings on missing fields, README caveat about "API-reported usage; may differ from billing surface."
3. **`~/.claude/settings.json` mutation.** `csm install-hooks` always backs up to `*.bak.<timestamp>` before writing. The merger preserves all unrelated keys.
4. **Keychain access.** A user with MDM lockout may not be able to write to Keychain. `csm install` detects this and exits with a clear error.
5. **Tailscale Serve reliability.** If the user's tailnet is misconfigured, the dashboard won't be reachable. `csm doctor` checks `tailscale serve status`.
6. **launchd on first install.** If the agent fails to bootstrap (e.g., Tailscale not running yet), KeepAlive will retry. Logs go to `~/Library/Logs/claude-sidecar-monitor/`.
7. **Hook script availability for non-shell-spawned claude.** The receiver assumes `claude` is invoked with `--setting-sources=user,project,local` (or the equivalent default behavior of reading `~/.claude/settings.json`). If a future Claude Code config blocks user settings, hooks won't fire. Mitigation: the JSONL watcher remains an independent ingestion path.

---

## 11. Repo layout

```
claude-sidecar-monitor/
├── CLAUDE.md
├── LICENSE
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── Makefile
├── .editorconfig
├── .gitignore
├── .mcp.json                  # project-scoped MCP servers (Playwright)
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── .husky/
│   └── commit-msg
├── docs/
│   ├── spec.md                # this file
│   ├── architecture.md
│   ├── gate-result.md         # populated by `csm doctor --gate-test`
│   ├── HANDOFF.md
│   ├── verification-matrix.md
│   └── decisions/
│       ├── 001-backend-language.md
│       ├── 002-sqlcipher-binding.md
│       └── 003-distribution.md
├── packages/
│   ├── collector/
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   ├── src/csm/...
│   │   └── tests/...
│   └── dashboard/
│       ├── package.json
│       ├── vite.config.ts
│       ├── tailwind.config.js
│       ├── tsconfig.json
│       ├── index.html
│       ├── public/
│       │   ├── icon-192.png
│       │   ├── icon-512.png
│       │   └── apple-touch-icon-180.png
│       └── src/...
└── scripts/
    ├── launchd/
    │   └── com.hank.claude-sidecar-monitor.plist.template
    └── tailscale-serve.sh
```
