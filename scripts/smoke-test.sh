#!/usr/bin/env bash
# Smoke test for Agentic Payment Merchant Demo (no LLM / HEG required for basic checks)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

check() {
  local name="$1"
  local url="$2"
  if curl -sf "$url" >/dev/null; then
    echo "OK  $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL $name ($url)"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Smoke Test ==="

check "Merchant Management API" "http://127.0.0.1:9100/health"
check "Merchant Registry" "http://127.0.0.1:9100/api/v1/registry/merchants"
check "Adapter Health" "http://127.0.0.1:8200/health"
check "UCP Discovery" "http://127.0.0.1:8200/.well-known/ucp"
check "Shopping Agent" "http://127.0.0.1:8090/a2a/shopping_agent/.well-known/agent-card.json"
check "Web Chat Client" "http://127.0.0.1:5183"
check "HEG Flight Backend" "http://127.0.0.1:9000/health"

echo ""
echo "Passed: $PASS  Failed: $FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  echo "Some services are not running. See docs/RUNBOOK.md"
  exit 1
fi
echo "All checks passed."
