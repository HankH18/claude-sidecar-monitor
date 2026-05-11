# claude-sidecar-monitor (`csm`)

<!-- Keep under ~200 lines. Claude reads this every turn. -->

## What this is

macOS-resident observability dashboard for Claude Code agent sessions, accessed from a phone via PWA over Tailscale Serve. Answers three glance-questions: what agents are running, are any hung, where are tokens going. Stores full transcripts for debugging and pushes ntfy notifications on hang/done.

User: solo developer (Hank). Deploy surface: a single Mac, launchd-managed daemon. v0.1.0 target.

## Stack

- **Backend (`packages/collector/`):** Python 3.12 + FastAPI + `uv`. Distributed via `uv tool install` (not PyInstaller). Listens on `127.0.0.1:8765`.
- **Frontend (`packages/dashboard/`):** React 18 + Vite + TypeScript + Tailwind. PWA. `react-arborist` for the agent tree.
- **Storage:** SQLCipher (`pysqlcipher3` against Homebrew `sqlcipher`) at `~/Library/Application Support/claude-sidecar-monitor/store.db`. Argon2id-derived key, cached in macOS Keychain.
- **Distribution:** launchd LaunchAgent + Tailscale Serve. ntfy.sh for notifications.

## Build & test

From repo root:

- `make bootstrap` — install collector deps (`uv sync`) and dashboard deps (`bun install`).
- `make dev` — run collector + dashboard dev servers concurrently.
- `make test` — run pytest + vitest.
- `make lint` — ruff + biome.
- `make typecheck` — mypy + tsc.
- `make build` — build dashboard static bundle.
- `make format` — auto-fix lint.

Per-package:

- Collector: `cd packages/collector && uv run pytest`, `uv run ruff check .`, `uv run mypy --strict src`.
- Dashboard: `cd packages/dashboard && bun run test`, `bun run lint`, `bun run typecheck`, `bun run build`.

CLI (after `uv tool install ./packages/collector`):

- `csm start` — foreground dev (uvicorn).
- `csm install` — first-time bootstrap (passphrase, hooks, launchd, ntfy topic).
- `csm doctor` — diagnostics.
- See `csm --help` for the full surface.

## Topology

- `packages/collector/` — Python backend (FastAPI app, hook receiver, JSONL watcher, scanner, aggregator, API, CLI).
  - `src/csm/{db,crypto,hooks,jsonl,scanner,tokens,tree,api,ntfy,cli}/`
  - `tests/{db,crypto,hooks,jsonl,scanner,tokens,tree,api}/`
- `packages/dashboard/` — React PWA (Overview, Project detail, Session detail, Tokens, Settings).
  - `src/{pages,components,api,hooks}/`
- `docs/` — spec, architecture, decisions, verification matrix.
- `scripts/` — launchd plist template, Tailscale serve setup.
- `.github/workflows/` — CI + release.
- `.claude/` — agent config.

## Conventions

- Match existing patterns. Search before inventing — Grep first.
- New files mirror nearest-neighbor structure.
- Conventional Commits enforced by Husky + commitlint (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`, `build:`, `refactor:`).
- Tests required for new code paths.
- Schema changes happen via new migration files (`packages/collector/src/csm/db/migrations/NNN_name.sql`); never edit a migration that has run.
- All token math comes from JSONL `usage` blocks per assistant turn — never from API/Admin endpoints (we don't have access).
- Server-side timestamps for hook events (the shell hook script can't reliably produce millisecond timestamps on macOS BSD `date`).

## Guardrails (never do these)

- Never commit secrets, `.env` files, or credentials.
- Never push directly to `main` / `master`. Branch + PR.
- Never modify generated artifacts (`dist/`, `build/`, `__pycache__/`).
- Never disable a test to get green. Fix the cause or ask.
- Never rewrite migrations that have run anywhere.
- Never log the user's passphrase or derived encryption key.
- Never write to `~/.claude/settings.json` without backing up first to a timestamped `.bak`.

## Sub-agents (use them)

Defined in `.claude/agents/`:

- `planner` (Opus) — call BEFORE coding any feature touching >2 files.
- `code-reviewer` (Opus) — call AFTER a feature, before commit. Catches subtle correctness/security issues.
- `test-runner` (Sonnet) — call instead of running tests inline; saves context.
- `debugger` (Opus) — call when a test fails or behavior is unexpected. Root-cause analysis, not pattern-matching.

**Run agents in parallel whenever the work is independent.** Multiple Agent tool calls in a single response execute concurrently. Sequence only when one agent's output is a required input to the next.

## Slash commands

- `/plan <request>` — invoke planner sub-agent
- `/review [target]` — invoke code-reviewer
- `/ship [msg]` — test + commit (no push)

## Canonical references

- `docs/spec.md` — the authoritative build spec (supersedes the Intent-era spec).
- `docs/architecture.md` — diagrams + sequence flows.
- `docs/HANDOFF.md` — current state + what the next session should pick up.
- `docs/decisions/` — ADRs (backend language, SQLCipher binding, distribution mechanism).
- `docs/verification-matrix.md` — every spec MUST mapped to a test or doc step.

## Failure modes (lessons learned)

- The original spec assumed `sqlcipher3-binary` (PyPI wheel). **Switched to `pysqlcipher3` against Homebrew `sqlcipher`** because the binary wheel lags releases and breaks on Apple Silicon bundling. Requires `brew install sqlcipher` as a build step.
- The original spec called for PyInstaller single-binary distribution. **Switched to `uv tool install`** because Apple Developer ID isn't available; PyInstaller binaries trigger Gatekeeper warnings, and `uv tool` is dramatically simpler.
- The Intent-era spec referred to "Spaces". **In Claude Code terminology these are Projects** (worktree groupings).
- Hook script timestamps via `date +%3N` are GNU-only — macOS BSD `date` expands `%3N` literally. **Server-side timestamping in the receiver only.**
