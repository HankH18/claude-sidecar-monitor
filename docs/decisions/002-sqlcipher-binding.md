# ADR 002 — SQLCipher binding: pysqlcipher3 + Homebrew sqlcipher

**Status:** Accepted (2026-05-10)
**Supersedes:** Intent-era spec choice of `sqlcipher3-binary` (PyPI wheel).

## Context

The collector stores prompts, diffs, and transcripts at rest. The Intent-era spec required SQLCipher at-rest encryption. Two options exist for Python:

1. **`sqlcipher3-binary`** — a PyPI wheel that bundles SQLCipher and Python bindings.
2. **`pysqlcipher3`** — a Python wrapper that links against a system-installed SQLCipher library (e.g., from Homebrew).

## Decision

Use **`pysqlcipher3`** linked against `brew install sqlcipher`.

## Rationale

- `sqlcipher3-binary`'s release cadence has historically lagged upstream SQLCipher, leaving security patches unapplied for months.
- Bundling SQLCipher in a binary wheel breaks reliably on Apple Silicon when packaged into a redistributable (PyInstaller, py2app, etc.). Our distribution is `uv tool install` (ADR-003), so the user's Python environment imports `_sqlcipher.so`, which links against `/opt/homebrew/lib/libsqlcipher.dylib`. This is straightforward and gets security updates via `brew upgrade`.
- Audit trail is clearer: SQLCipher version is whatever `brew info sqlcipher` reports, not a vendored snapshot of unknown vintage.

## Consequences

- `csm install` checks for Homebrew `sqlcipher` and aborts with a clear error if missing.
- The README quickstart includes `brew install sqlcipher` as a prerequisite (one-line, ~30s).
- CI runs `brew install sqlcipher` on the macos-latest runner before `uv sync`.
- `pysqlcipher3` has slightly fewer downloads than the binary wheel; we document it in CONTRIBUTING.

## Alternatives considered

- **App-layer encryption** with `cryptography` over plain SQLite: rejected because it loses transparent-column queries on encrypted blobs and adds custom code we'd have to maintain.
- **`sqlcipher3-binary` with a fallback to system SQLCipher**: rejected — too much complexity for v0.1.
