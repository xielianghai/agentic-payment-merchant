#!/usr/bin/env bash
# Stop buyer/cp/mpp HTTP MCP started by heg-flight start-backend.sh.
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERCHANT_HOME="${MERCHANT_HOME:-}"
if [ -z "$MERCHANT_HOME" ]; then
  SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  MERCHANT_HOME="$(cd "$SKILL_DIR/../../.." && pwd)"
fi
PAYMENT_STACK="$MERCHANT_HOME/payment-stack"

# shellcheck disable=SC1091
source "$PAYMENT_STACK/scripts/demo_lib.sh"
demo_lib_init_minimal

OPENCLAW_PID_FILE="$PAYMENT_STACK/.run-qclaw-heg/pids"
BUYER_MCP_PORT="${UNIFIED_BUYER_MCP_PORT:-8100}"
CP_MCP_PORT="${UNIFIED_CP_MCP_PORT:-8102}"
MPP_MCP_PORT="${UNIFIED_MPP_MCP_PORT:-8103}"

if [ -f "$OPENCLAW_PID_FILE" ]; then
  echo "Stopping HEG Flight buyer MCP processes..."
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    kill -TERM "$pid" 2>/dev/null || true
  done < "$OPENCLAW_PID_FILE"
  sleep 1
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done < "$OPENCLAW_PID_FILE"
  rm -f "$OPENCLAW_PID_FILE"
fi

for port in "$BUYER_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT"; do
  demo_kill_port "$port"
done

echo "Done."
