# ADR 001 — Backend language: Python 3.12 + FastAPI + uv

**Status:** Accepted (2026-05-10, ratified at Claude Code handoff)
**Supersedes:** Original Intent-era spec recommendation of TypeScript on Bun + Hono.

## Context

The collector daemon must:

- Read and write an encrypted SQLite database (full prompts and diffs at rest).
- Watch `~/.claude/projects/` for JSONL transcript appends with low latency on macOS.
- Hash a passphrase into a database key and cache it in the macOS Keychain.
- Run as a long-lived launchd-managed daemon.
- Expose a small HTTP + SSE surface and a Typer-style CLI.

## Decision

Use **Python 3.12** with **FastAPI** + `uvicorn[standard]`, managed with **`uv`**.

Distribution mechanism: see ADR-003 (this was originally PyInstaller; switched to `uv tool install`).

## Rationale

- **SQLCipher bindings.** `pysqlcipher3` is a maintained Python wrapper that compiles against the Homebrew `sqlcipher` library. (Why not the `sqlcipher3-binary` PyPI wheel: see ADR-002.)
- **Argon2id and Keychain.** `argon2-cffi` and `keyring` (with the macOS backend) are well-trodden; the latter wraps `security` directly. Both compose cleanly with `pysqlcipher3`.
- **FSEvents watcher.** `watchdog` provides a battle-tested FSEvents adapter for the JSONL ingestion path.
- **Ergonomics.** FastAPI + Typer give us OpenAPI for free and a clean CLI surface with minimal ceremony.
- **User preference.** Hank prefers Python for daemon work and is standardising on it.

## Consequences

- Frontend remains TypeScript / React / Vite; collector and dashboard share no runtime, talking only over HTTP + SSE.
- T4's `db.connect(key: str | None = None)` signature must be stable so T29 can pass the derived key.
- Type-checking is `mypy --strict` over `packages/collector/src`.
- Distribution is `uv tool` (ADR-003).

## Layout

```
packages/collector/
├── pyproject.toml
├── src/csm/
│   ├── __init__.py
│   ├── server.py
│   ├── cli/
│   ├── db/
│   ├── crypto/
│   ├── hooks/
│   ├── jsonl/
│   ├── scanner/
│   ├── tokens/
│   ├── tree/
│   ├── api/
│   └── ntfy/
└── tests/
```
