#!/usr/bin/env bash
# Run every check CI runs, on your own machine, before you push (Linux / macOS / Git Bash).
#   ./scripts/check.sh               install deps, lint, tests, build
#   ./scripts/check.sh --no-install  skip installs (used by the pre-push hook)
#   ./scripts/check.sh --docker      also runs the full Docker smoke test
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n==> %s\n' "$1"; }

INSTALL=1
DOCKER=0
for arg in "$@"; do
  case "$arg" in
    --no-install) INSTALL=0 ;;
    --docker) DOCKER=1 ;;
  esac
done

step "Air-gap check";        python scripts/check_airgap.py
if [ "$INSTALL" = 1 ]; then
  step "API: install";       (cd api && uv sync --frozen)
fi
step "API: format check";    (cd api && uv run ruff format --check .)
step "API: lint";            (cd api && uv run ruff check .)
step "API: tests";           (cd api && uv run pytest)
if [ "$INSTALL" = 1 ] || [ ! -d web/node_modules ]; then
  step "Web: install";       (cd web && npm ci)
fi
step "Web: all checks";      (cd web && npm run check)
if [ "$DOCKER" = 1 ]; then step "Docker smoke test"; bash scripts/smoke_test.sh; fi
printf '\nAll checks passed.\n'
