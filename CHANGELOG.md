# Changelog

All notable changes to `claude-sidecar-monitor` will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial repo scaffolding (collector + dashboard packages, CI, Husky, Makefile, docs).
- Hook receiver (POST /hook/<event>), JSONL watcher (FSEvents tail), hang scanner (5s loop), token aggregator (debounced subscriber), agent tree builder (Task-edge heuristic).
- REST + SSE API: /api/state, /api/sessions/:id (+ transcript), /api/tree, /api/tokens, /api/settings (GET+PATCH), /api/test-notification, /stream.
- ntfy.sh dispatcher (hung priority 5, top-level done priority 3, waiting_user priority 4).
- Dashboard pages (PWA, mobile-first, dark): Overview, Project detail (react-arborist tree), Session detail (transcript reader + scrubber + j/k nav), Tokens (top sessions/projects/by-model + 14-day chart), Settings.
- Dashboard UX: Toast queue, ConfirmDialog, Breadcrumbs, ConnectionBanner (with reconnect retry + transition toasts), pull-to-refresh, EmptyState illustrations, Skeleton placeholders, ConnectionStatus indicator, ErrorBoundary, relative time formatter.
- At-rest encryption: SQLCipher + Argon2id KDF + macOS Keychain. `csm change-passphrase` rotates atomically.
- `csm` CLI: version, start, install, install-hooks (+ --dry-run, --uninstall), install-launchd, uninstall, doctor (+ --gate-test), change-passphrase, purge (+ --reset-passphrase).
- launchd plist template, Tailscale Serve setup script.
- docs: spec.md, architecture.md (4 Mermaid diagrams), verification-matrix.md (38 rows), three ADRs (backend language, SQLCipher binding, distribution), HANDOFF.md.

### Quality

- 249 tests pass (175 backend + 74 frontend), 1 skipped.
- ruff + ruff format + mypy --strict + biome + tsc + vite build all clean.
- Dashboard bundle: 376 KB JS / 38 KB CSS / PWA precache 405 KiB.

[Unreleased]: https://github.com/HankH18/claude-sidecar-monitor/compare/HEAD...HEAD
