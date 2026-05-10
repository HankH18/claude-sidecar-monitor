# csm — collector daemon

The Python backend for `claude-sidecar-monitor`. FastAPI + uvicorn, packaged with `uv`.

## Local development

```bash
brew install sqlcipher

cd packages/collector
SQLCIPHER_PATH="$(brew --prefix sqlcipher)" \
LDFLAGS="-L${SQLCIPHER_PATH}/lib" \
CPPFLAGS="-I${SQLCIPHER_PATH}/include" \
uv sync

uv run pytest                      # smoke test
uv run csm start --reload          # run dev server on :8765
curl http://127.0.0.1:8765/healthz
```

## Layout

See `docs/spec.md` §6 for the full module map. v0.1 ships:

- `csm.server` — FastAPI app, `/healthz`.
- `csm.cli` — Typer entrypoint (`csm version`, `csm start`).
- `csm.config` — paths and env-var overrides.
- `csm.bus` — in-process asyncio pub/sub for ingestion fan-out.

Phases 2–6 add `db/`, `crypto/`, `hooks/`, `jsonl/`, `scanner/`, `tokens/`, `tree/`, `api/`, `ntfy/`.

## Tests

```bash
uv run pytest                      # all tests
uv run pytest tests/db             # one module
uv run ruff check .                # lint
uv run mypy --strict src           # types
```

## Install as a tool

From the repo root:

```bash
uv tool install ./packages/collector
csm version
```
