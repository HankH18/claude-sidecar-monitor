# ADR 003 — Distribution: `uv tool install`, not PyInstaller

**Status:** Accepted (2026-05-10)
**Supersedes:** Intent-era spec choice of PyInstaller single-binary.

## Context

The collector ships as a CLI (`csm`) plus a launchd-managed FastAPI daemon. The Intent-era spec called for a single-binary `dist/csm` produced by PyInstaller, "so end users do not need a Python runtime installed."

Two complications:

1. **Apple Developer ID for notarization.** Hank doesn't have one. Without notarization, an unsigned binary triggers Gatekeeper warnings ("cannot be opened because the developer cannot be verified"). The user must `xattr -d com.apple.quarantine` or right-click → Open. For a tool the user installs themselves, this is friction without payoff.
2. **PyInstaller + native deps.** SQLCipher (ADR-002) links against a Homebrew dylib. Bundling that into a redistributable PyInstaller binary on Apple Silicon is fragile.

## Decision

Distribute `csm` as a **`uv tool`-installable Python package**:

```bash
brew install sqlcipher
uv tool install ./packages/collector       # local install for v0.1
# OR after PyPI publish (v0.2+):
uv tool install csm
```

`uv tool` creates an isolated venv per tool with a binary shim in `~/.local/bin/csm`. No system Python needed (uv-managed Python via `uv python install 3.12`).

## Rationale

- **Simpler.** Skips the entire PyInstaller spec, native-dep bundling, and code-signing dance.
- **Updates trivially.** `uv tool upgrade csm` replaces the venv contents.
- **No Gatekeeper friction.** `~/.local/bin/csm` is just a shim, not a "downloaded executable."
- **Honest about runtime.** `csm install` already checks for Homebrew `sqlcipher`; checking for `uv` is one more line and an actionable error message.

## Consequences

- launchd plist (`scripts/launchd/com.hank.claude-sidecar-monitor.plist.template`) points at `~/.local/bin/csm` (path is templated; `csm install-launchd` substitutes the actual path).
- The release workflow (`.github/workflows/release.yml`) does NOT build a binary asset. Instead, on tag `v*` it publishes to PyPI (or, for v0.1, attaches a sdist + wheel to the GitHub Release for `uv tool install <url>`).
- README quickstart is shorter (no "right-click Open" instructions).
- Cold-start latency for `csm doctor`/`csm version` is ~50–100 ms (Python import time), not the ~500 ms of a PyInstaller-frozen binary.

## Alternatives considered

- **Homebrew tap.** Reasonable; `brew tap hankholcomb/csm && brew install csm`. Deferred — `uv tool` is sufficient for v0.1 and a tap is easy to add for v0.2.
- **Notarized PyInstaller binary.** Requires Apple Developer ID ($99/yr) which Hank doesn't have.
- **Docker.** Rejected — launchd-managed FastAPI daemon doesn't need containerization, and macOS Docker setups are heavier than the tool deserves.
