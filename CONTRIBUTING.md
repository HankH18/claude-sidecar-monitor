# Contributing to claude-sidecar-monitor

Thanks for considering a contribution. This project is small and intentionally scoped — see [`docs/spec.md` §9](docs/spec.md#9-non-goals-deferred-to-v2) for things explicitly out of scope.

## Development setup

```bash
brew install sqlcipher
uv python install 3.12
git clone https://github.com/HankH18/claude-sidecar-monitor
cd claude-sidecar-monitor
make bootstrap     # uv sync (collector) + bun install (dashboard)
make test          # pytest + vitest
make lint          # ruff + biome
make typecheck     # mypy + tsc
```

The collector and dashboard are independent packages and talk only over HTTP + SSE.

- `packages/collector/` — Python 3.12 + FastAPI. `uv run pytest`, `uv run ruff check .`, `uv run mypy --strict src`.
- `packages/dashboard/` — React + Vite + TS. `bun run test`, `bun run typecheck`, `bun run build`.

## Conventional Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(api): add /api/tokens daily totals endpoint
fix(scanner): preCompact extension was off by 1000ms
docs(spec): clarify state machine transitions
test(crypto): add wrong-passphrase rejection case
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `test`, `ci`, `build`, `refactor`. Scope is optional but encouraged when it clarifies (`feat(db):`, `feat(crypto):`).

A Husky `commit-msg` hook runs commitlint locally. `git commit -m "bad message"` will be rejected.

## Branch protection

`main` does not accept direct pushes. Open a PR against `main`; CI must pass:
- collector: ruff + mypy --strict + pytest
- dashboard: biome + tsc + vitest + build

## Running the receiver locally for development

```bash
cd packages/collector
uv run uvicorn csm.server:app --reload --port 8765
```

Then in another terminal, install the hook script (or run with `CSM_DB_PATH=/tmp/csm.db` for a throwaway DB):

```bash
csm install-hooks --dry-run         # see what would change in ~/.claude/settings.json
csm install-hooks                   # actually install
claude -p "echo hello"              # should appear in the receiver's logs
```

## Database migrations

New schema changes go in a new file:

```
packages/collector/src/csm/db/migrations/NNN_descriptive_name.sql
```

Where `NNN` is the next sequential 3-digit number. **Never edit a migration that has already run** — write a new migration that mutates the schema.

## Releases

Releases follow [Semantic Versioning](https://semver.org). v0.x.y is allowed to have minor breaking changes between minor versions.

Tagging `vX.Y.Z` triggers `.github/workflows/release.yml` which builds the wheel + sdist and attaches them to the GitHub Release.

## Reporting bugs

Open an issue with:

1. macOS version + chip (Intel / Apple Silicon).
2. `csm version` output.
3. `csm doctor` output (redact ntfy_topic).
4. Steps to reproduce.

For hook-related issues, attach the relevant `~/Library/Logs/claude-sidecar-monitor/collector.log` excerpt.
