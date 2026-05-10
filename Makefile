# claude-sidecar-monitor — convenience targets
#
# Fans out to packages/collector (uv) and packages/dashboard (bun).
# Re-runs are cheap when nothing changed.

SHELL := /bin/bash
.PHONY: help bootstrap dev test lint format typecheck build clean check icons

# Bun isn't always on a fresh shell PATH; the official installer puts it
# at ~/.bun/bin. Prefer that, fall back to whatever's on PATH.
BUN := $(shell command -v bun 2>/dev/null || echo "$(HOME)/.bun/bin/bun")

# Homebrew sqlcipher (ADR-002) — exposed to uv sync so pysqlcipher3 compiles
SQLCIPHER_PATH := $(shell brew --prefix sqlcipher 2>/dev/null)
SQLCIPHER_ENV := \
  SQLCIPHER_PATH="$(SQLCIPHER_PATH)" \
  LDFLAGS="-L$(SQLCIPHER_PATH)/lib" \
  CPPFLAGS="-I$(SQLCIPHER_PATH)/include" \
  CFLAGS="-I$(SQLCIPHER_PATH)/include"

help:
	@echo "Targets:"
	@echo "  bootstrap    install all deps (uv sync + bun install)"
	@echo "  dev          run collector + dashboard dev servers (concurrent)"
	@echo "  test         run all tests (pytest + vitest)"
	@echo "  lint         ruff + biome"
	@echo "  format       auto-fix lint"
	@echo "  typecheck    mypy --strict + tsc"
	@echo "  build        build dashboard static bundle"
	@echo "  check        lint + typecheck + test"
	@echo "  icons        regenerate PWA placeholder icons"
	@echo "  clean        remove build artifacts and caches"

bootstrap:
	@if [ -z "$(SQLCIPHER_PATH)" ]; then \
	  echo "ERROR: brew install sqlcipher first (ADR-002)"; exit 1; \
	fi
	cd packages/collector && $(SQLCIPHER_ENV) uv sync
	cd packages/collector && $(SQLCIPHER_ENV) uv pip install -e .
	cd packages/dashboard && $(BUN) install

dev:
	@echo "Starting collector on :8765 and dashboard on :5173 (Ctrl-C to stop both)"
	@trap 'kill 0' INT TERM EXIT; \
	  (cd packages/collector && uv run csm start --reload) & \
	  (cd packages/dashboard && $(BUN) run dev) & \
	  wait

test:
	cd packages/collector && uv run pytest
	cd packages/dashboard && $(BUN) run test

lint:
	cd packages/collector && uv run ruff check .
	cd packages/dashboard && $(BUN) run lint

format:
	cd packages/collector && uv run ruff check --fix . && uv run ruff format .
	cd packages/dashboard && $(BUN) run format

typecheck:
	cd packages/collector && uv run mypy --strict src
	cd packages/dashboard && $(BUN) run typecheck

build:
	cd packages/dashboard && $(BUN) run build

check: lint typecheck test

icons:
	/usr/bin/python3 scripts/generate-icons.py

clean:
	rm -rf packages/collector/.venv packages/collector/.pytest_cache packages/collector/.mypy_cache packages/collector/.ruff_cache packages/collector/dist packages/collector/build
	rm -rf packages/dashboard/dist packages/dashboard/dev-dist packages/dashboard/node_modules
