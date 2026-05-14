# claude-sidecar-monitor — Build Handoff

This file tracks the project's current state for future development sessions.

---

## Current state (2026-05-10, end of overnight build + 2 self-improvement rounds)

**Branch:** `main`
**Working tree:** clean
**Tests:** ✅ 175 backend + 74 frontend = **249 total, 1 skipped** (SSE-via-pytest hangs; manual verification works)
**Quality gates:** ruff + ruff format + mypy --strict + biome + tsc + vite build all clean
**Bundle:** 376 KB JS / 38 KB CSS / PWA precache 405 KiB across 9 entries

`make test`, `make lint`, `make typecheck`, `make build`, `make check` all green.

## What's done — every phase

| Phase | Tasks | Status | Commit |
|---|---|---|---|
| 0 — Repo prep + docs | spec.md, ADRs, README, CONTRIBUTING, CLAUDE.md, dotfiles, license | ✅ | `2c47660`, `3e3db54` |
| 1 — Scaffolding | collector + dashboard packages, CI, Husky, Makefile, PWA icons | ✅ | `9e6b9ea`, `991faab` |
| 2 — DB + crypto | SQLCipher schema (T4), Argon2id + Keychain encryption (T29) | ✅ | `7a96578` |
| 3 — Ingestion | Hook receiver (T6), JSONL watcher (T7) | ✅ | `8c5f5a6` |
| 4 — Processors | Hang scanner (T8), token aggregator (T9), tree builder (T10) | ✅ | `4cb7861`, `73e1057` |
| 5 — API + dispatcher | REST + SSE (T11), ntfy (T12) | ✅ | `15939e6` |
| 6 — CLI + deployment | Typer CLI (T13), launchd plist (T14), Tailscale serve (T15) | ✅ | `e7a2ada`, `366640c` |
| 7 — Dashboard | All 5 pages with mocks (T16–T20) + live wire-up | ✅ | `7156f05`, `f96b14a` |
| 8 — Polish + docs | architecture.md (T25), verification-matrix.md (T28) | ✅ | `43d0d63` |
| 9 — Final pass | Verification matrix refresh + HANDOFF rewrite | ✅ | `368d1ef` |
| Round 1 — Design polish | Theme tokens, EmptyState, Skeleton, animate-pulse-ring, focus rings, ≥44pt touch targets, semantic intent buttons | ✅ | `4813ce3` |
| Round 2 — UX polish | Toast queue, ConfirmDialog, Breadcrumbs, ConnectionBanner, pull-to-refresh, transcript scrubber + j/k nav, relative time formatter, ntfy topic generator + preview | ✅ | `dee5a77` |

`v0.1.0-rc1` candidate. Two known release-day items remain — see "What's left for the user" below.

## Quick reference

**Repo:** `/Users/hankholcomb/Documents/personal_repos/claude-sidecar-monitor`
**Stack:** Python 3.12 + FastAPI + uv (collector), React 18 + Vite + TS + Tailwind (dashboard PWA)
**Storage:** SQLCipher via `sqlcipher3` against Homebrew sqlcipher; Argon2id key in macOS Keychain
**Listener:** `127.0.0.1:8765`
**DB:** `~/Library/Application Support/claude-sidecar-monitor/store.db`
**JSONL:** `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
**Distribution:** `uv tool install` (no PyInstaller)
**Notifications:** ntfy.sh (public), topic in settings DB
**Reachability:** Tailscale Serve

## What's left for the user (post-overnight)

These need a real Mac, real iPhone, or one-way actions only the user should authorise:

1. **Run `csm install`** on your Mac (mutates `~/.claude/settings.json`, Keychain, launchd). Reversible via `csm uninstall`.
2. **Run `./scripts/tailscale-serve.sh`** to bind the dashboard to your tailnet. Needs Tailscale running.
3. **iPhone Add-to-Home-Screen** at `https://<mac>.<tailnet>.ts.net/`. Confirm dark theme + custom icon + standalone.
4. **`gh repo create hankholcomb/claude-sidecar-monitor --public --source=. --push`** when you're ready to go public.
5. **Tag v0.1.0** when you've walked the verification matrix's manual rows. See `docs/verification-matrix.md` "How to re-run".
6. **Capture artwork:**
   - T22 install GIF (asciinema or vhs of `csm install`).
   - T23 iPhone screenshots (Overview / Project / Tokens).
   - T24 ~60s demo video.

Apple Developer ID isn't required (ADR-003: distribution via `uv tool install`, not PyInstaller). v0.1 ships unsigned.

## Quickstart on a fresh Mac

```bash
brew install sqlcipher
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/HankH18/claude-sidecar-monitor
cd claude-sidecar-monitor
make bootstrap
make check          # lint + typecheck + test (all green)
make dev            # collector on :8765, dashboard on :5173
```

For the launchd-managed daemon path:

```bash
uv tool install ./packages/collector
csm install         # passphrase prompt, hooks merge, plist install, ntfy topic
csm doctor          # ✓/✗ across hooks/launchd/collector/Keychain/sqlcipher/ntfy
csm doctor --gate-test  # synthetic SessionStart end-to-end through the receiver
```

## Architecture quick read

See [`docs/architecture.md`](architecture.md) for the long form (4 Mermaid diagrams: hook→SSE sequence, ER schema, state machine, encryption flow).

Two ingestion sources:
- **Hooks** — `POST /hook/<event>`, low-latency state machine driver. Receiver runs `csm.hooks.state_machine.apply_event`.
- **JSONL** — watchdog-tailed transcripts, authoritative for token usage and full prompt/response content.

Five background tasks share an in-process `csm.bus` (`asyncio.Queue` fan-out): receiver-publisher, JSONL watcher, hang scanner, token aggregator, ntfy dispatcher. SSE multiplexer (`/stream`) subscribes and pushes to dashboards.

## Lessons learned (carried forward)

1. **Auto-commit is not a thing under Claude Code.** Each commit is intentional, Conventional Commits, per logical unit. (Was a recurring concern in the Intent-era spec — irrelevant here.)
2. **Server-side timestamps for hook events.** Shell hook script can't reliably produce ms timestamps on macOS BSD `date` (no `%3N`). All `received_at` values come from `csm.hooks.state_machine.utcnow_iso`.
3. **`~/.claude/settings.json` mutation always backs up to `*.bak.<timestamp>`** before any merge. Implemented in `csm.cli.hooks` with idempotent re-run + dry-run.
4. **Don't log the passphrase or derived key.** Audit-grep your logs.
5. **Hook payloads carry `transcript_path`.** Use that, don't reconstruct `~/.claude/projects/<encoded-cwd>/...` from scratch.
6. **Intent's bundled `claude` is a different binary** than the user's PATH `claude`. Verifier matrix re-runs a gate-style smoke test at release time.
7. **SQLCipher `executescript` in autocommit mode auto-commits each statement** — explicit BEGIN/COMMIT around `executescript` doesn't survive. Migrations rely on `IF NOT EXISTS` / `OR IGNORE` instead.
8. **`uv sync`'s editable install on hatchling can lose its `.pth` registration** under our uv version. Tests use `pythonpath = ["src"]` in `pyproject.toml` to bypass; production install via `uv pip install -e .` works.
9. **`check_same_thread=False` on the SQLCipher connection.** Required because FastAPI's threadpool + watchdog's observer share the connection. WAL mode handles concurrent access.
10. **Vitest 3 + Vite 6 are required.** Vitest 2's bundled vite version conflicts with the top-level vite; tsc surfaces it as a plugin-type mismatch.
11. **Husky's commit-msg hook needs `bunx` OR `npx` on the hook's PATH.** The hook script tries both with a clear error if neither is found.

## How sub-agents collaborated

Six general-purpose sub-agents over the overnight + self-improvement run, all on non-overlapping file scopes:

- `aee56d764b11853f5` — launchd plist + Tailscale script + README "phone reach" section
- `a4043b9d8282cbe85` — CLI commands (T13)
- `af289e758e770549d` — frontend live-mode wire-up (mock → real /api/* + SSE) + ConnectionStatus + ErrorBoundary
- `ac7328eb74c6ba5bd` — architecture.md (4 Mermaid diagrams) + verification-matrix.md (38 rows)
- `acc5eb71beeed7e68` — Round 1 design polish (theme tokens, EmptyState, Skeleton, animate-pulse-ring, focus rings, touch targets)
- `ae9e2c031b57b0286` — Round 2 UX polish (toasts, ConfirmDialog, breadcrumbs, ConnectionBanner, pull-to-refresh, scrubber + j/k nav, relative time, ntfy preview)

Each was scoped to a specific directory tree to avoid file conflicts. The coordinator (this session) committed every agent's work itself — sub-agents under sandbox can't pass the husky `commit-msg` hook reliably.

## Status of every spec acceptance criterion

See [`docs/verification-matrix.md`](verification-matrix.md) — 38 rows, no remaining ❌, the ⚠️ rows are documented manual steps for the release-day checklist.
