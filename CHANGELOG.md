# Changelog

All notable changes to `claude-sidecar-monitor` will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial repo scaffolding (collector + dashboard packages, CI, docs).
- Hook receiver, JSONL watcher, hang scanner, token aggregator, agent tree builder.
- REST + SSE API, ntfy.sh dispatcher.
- Dashboard pages: Overview, Project detail, Session detail, Tokens, Settings.
- At-rest encryption (SQLCipher + Argon2id + macOS Keychain).
- `csm` CLI: install, install-hooks, install-launchd, uninstall, doctor, change-passphrase, purge.

[Unreleased]: https://github.com/hankholcomb/claude-sidecar-monitor/compare/HEAD...HEAD
