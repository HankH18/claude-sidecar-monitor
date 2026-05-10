# claude-sidecar-monitor — Build Handoff

This file tracks the project's current state for future development sessions. It is **updated at the end of every working session** with a tight description of what's done, what's pending, and what blockers exist.

---

## Current state

**Last updated:** 2026-05-10 (Phase 0 complete)
**Working tree:** clean on `main`
**Tests:** N/A (scaffolding incomplete)

## What's done

- ✅ **Phase 0 — Repo prep + docs import (in progress at the time of this draft).** LICENSE, .editorconfig, CHANGELOG, README skeleton, CLAUDE.md, CONTRIBUTING.md, comprehensive `docs/spec.md`, three ADRs.

## What's in progress

- 🚧 **Overnight build, started 2026-05-10**, executing Phases 0–9 autonomously per the build plan in `docs/spec.md`. Realistic target: v0.1.0-rc1 by morning.

## What's pending (post-overnight)

These need the user's hand on the keyboard and won't happen autonomously:

- **`csm install`** — touches `~/.claude/settings.json`, launchd, Keychain. Reversible via `csm uninstall`, but requires the user to run it once on their actual Mac.
- **Tailscale Serve setup** — needs the user's tailnet account.
- **Apple Developer signing** — Hank doesn't have an Apple Developer ID, so v0.1 ships unsigned. Documented in ADR-003.
- **Demo artifacts** — install GIF (T22), iPhone screenshots (T23), demo video (T24) need real device + live system.
- **GitHub repo creation + first push** — `gh repo create hankholcomb/claude-sidecar-monitor --public --source=. --push`. The user gates this.
- **v0.1.0 signed tag + release** (T26) — gated by user.

## Build plan

See `docs/spec.md` for the canonical spec. The build is organized into phases:

| Phase | Tasks | Status |
|-------|-------|--------|
| 0 — Repo prep + docs import | LICENSE, README, CLAUDE.md, spec, ADRs | ✅ done |
| 1 — Scaffolding | Makefile, Husky, collector + dashboard skeletons, CI | ⏳ |
| 2 — DB + encryption | Schema, migrations, SQLCipher, Argon2id, Keychain | ⏳ |
| 3 — Ingestion | Hook receiver, JSONL watcher | ⏳ |
| 4 — Processors | Hang scanner, token aggregator, tree builder | ⏳ |
| 5 — API + dispatcher | REST + SSE, ntfy | ⏳ |
| 6 — CLI + deployment | Typer CLI, launchd plist, Tailscale script (write-only) | ⏳ |
| 7 — Dashboard pages | Overview, Project, Session, Tokens, Settings | ⏳ |
| 8 — Polish + verification | README, architecture.md, verification matrix | ⏳ |
| 9 — Final test run + summary | `make test` green, this file updated | ⏳ |

## Stack quick reference

- Backend: Python 3.12 + FastAPI + uv (`packages/collector/`)
- Frontend: React 18 + Vite + TS + Tailwind + PWA (`packages/dashboard/`)
- Storage: SQLCipher via `pysqlcipher3` against Homebrew `sqlcipher`; key in macOS Keychain
- Listener: `127.0.0.1:8765`
- DB: `~/Library/Application Support/claude-sidecar-monitor/store.db`
- JSONL: `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
- Distribution: `uv tool install` (no PyInstaller)

## Lessons learned (carried forward)

1. **Auto-commit is not relevant under Claude Code** (was an Intent-era concern). Claude Code commits when asked, per logical unit, Conventional Commits.
2. **Server-side timestamps** for hook events. The shell hook script can't reliably produce ms timestamps on macOS BSD `date` (no `%3N`).
3. **Backup `~/.claude/settings.json` always.** `csm install-hooks` writes a timestamped `.bak` before any merge.
4. **Don't log the passphrase or derived key.** Audit-grep your logs.
5. **Hook payloads carry `transcript_path`.** Use that, don't reconstruct `~/.claude/projects/<encoded-cwd>/...` from scratch.
6. **Intent's bundled `claude` is a different binary version** than the user's PATH `claude`. Verifier matrix (T28) re-runs a gate-style smoke test at release time.
