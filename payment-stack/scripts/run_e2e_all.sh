#!/bin/bash
# Run all unified AP2 E2E flows (stack must be up via ./start.sh).
set -eu

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export MONITOR_INTERVAL_MINUTES="${MONITOR_INTERVAL_MINUTES:-1}"
export SMOKE_MONITOR_TIMEOUT_S="${SMOKE_MONITOR_TIMEOUT_S:-120}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}"
export no_proxy="${no_proxy:-$NO_PROXY}"

FAIL=0
PASSED=()
FAILED=()

run_step() {
  local name="$1"
  shift
  echo ""
  echo "================================================================"
  echo "  $name"
  echo "================================================================"
  if "$@"; then
    echo ">>> PASSED: $name"
    PASSED+=("$name")
  else
    echo ">>> FAILED: $name" >&2
    FAILED+=("$name")
    FAIL=1
  fi
}

run_step "health + tool bridge" ./scripts/smoke_check.sh
run_step "shoe HNP + card" uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py
run_step "shoe HNP + x402" env SMOKE_PAYMENT_METHOD=x402 uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py
run_step "shoe HP + card" uv run --no-sync python scripts/e2e_shoe_hp.py
run_step "shoe HP + x402" env PAYMENT_METHOD=x402 uv run --no-sync python scripts/e2e_shoe_hp.py
run_step "flight HP + card" uv run --no-sync python scripts/e2e_flight_hp_card.py
run_step "flight HNP + card" uv run --no-sync python scripts/e2e_flight_hnp.py
run_step "buyer MCP smoke" uv run --no-sync python scripts/smoke_openclaw_buyer.py

echo ""
echo "================================================================"
echo "  SUMMARY"
echo "================================================================"
for n in "${PASSED[@]}"; do echo "  OK   $n"; done
if [ "${#FAILED[@]}" -gt 0 ]; then
  for n in "${FAILED[@]}"; do echo "  FAIL $n"; done
fi

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "Some flows failed (${#FAILED[@]} / $((${#PASSED[@]} + ${#FAILED[@]})))."
  exit 1
fi

echo ""
echo "All ${#PASSED[@]} flows passed."
exit 0
