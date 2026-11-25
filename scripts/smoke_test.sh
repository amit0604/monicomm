#!/usr/bin/env bash
# Starts the full stack, checks it works, and checks the air gap holds.
# Used by CI; developers can run it too (needs Docker).
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env
# Own port, so the test doesn't clash with anything already on 8080
PORT="${MONICOMM_SMOKE_PORT:-18080}"
export MONICOMM_HTTP_PORT="$PORT"

cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> Building and starting the stack"
docker compose up -d --build --wait --wait-timeout 300

echo "==> UI is served"
curl -fsS "http://localhost:${PORT}/" | grep -q '<div id="root">'

echo "==> API answers through the web proxy"
curl -fsS "http://localhost:${PORT}/api/v1/health" | grep -q '"status":"ok"'

echo "==> The api container has NO internet access (air gap)"
if docker compose exec -T api python -c "
import socket
socket.setdefaulttimeout(5)
socket.create_connection(('1.1.1.1', 443))
" >/dev/null 2>&1; then
  echo "FAIL: api container reached the internet. The backend network must be internal." >&2
  exit 1
fi

echo "Smoke test passed."
