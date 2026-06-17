#!/bin/bash
# Quick health check for unified demo services (run while ./run.sh is up).
set -eu

AGENT_PORT="${UNIFIED_AGENT_PORT:-8090}"
MERCHANT_PORT="${MERCHANT_TRIGGER_PORT:-8091}"
WEB_PORT="${UNIFIED_WEB_CLIENT_PORT:-5183}"

check() {
  local name="$1" url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
  if [ "$code" = "200" ] || [ "$code" = "204" ]; then
    echo "OK  $name ($code) $url"
  else
    echo "FAIL $name ($code) $url"
    return 1
  fi
}

fail=0
check "agent-card" "http://127.0.0.1:${AGENT_PORT}/a2a/shopping_agent/.well-known/agent-card.json" || fail=1
check "merchant-state" "http://127.0.0.1:${MERCHANT_PORT}/state?item_id=test" || fail=1
# Vite may bind IPv6-only (localhost); fall back from 127.0.0.1.
if ! check "web-client" "http://127.0.0.1:${WEB_PORT}/"; then
  check "web-client" "http://localhost:${WEB_PORT}/" || fail=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if (cd "${SCRIPT_DIR}/../roles/shopping_agent_unified" && uv run --no-sync python "${SCRIPT_DIR}/verify_unified_tools.py"); then
  echo "OK  unified mandate tool bridge"
else
  echo "FAIL unified mandate tool bridge (see verify_unified_tools.py)"
  fail=1
fi

exit $fail
