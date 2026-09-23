#!/usr/bin/env bash
# The single gate. Exits 0 only when every check passes.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "ruff (lint)";        uv run ruff check backend tests scripts
step "ruff (format)";      uv run ruff format --check backend tests scripts
step "mypy";               uv run mypy
step "pytest";             uv run pytest -q
step "tsc";                (cd frontend && npx tsc -b --noEmit)
step "eslint";             (cd frontend && npx eslint .)
step "vitest";             (cd frontend && npx vitest run)
step "frontend build";     (cd frontend && npm run build)
step "playwright (e2e)";   (cd frontend && npx playwright test)

printf '\n\033[32m\033[1mALL CHECKS PASSED\033[0m\n'
