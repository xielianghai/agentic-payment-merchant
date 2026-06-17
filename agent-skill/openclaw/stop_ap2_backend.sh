#!/bin/bash
# Stop AP2 openclaw mock backend (triggers + HTTP MCP).

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init_minimal

OPENCLAW_PID_FILE="$SCRIPT_DIR/.run-openclaw/pids"
BUYER_MCP_PORT="${UNIFIED_BUYER_MCP_PORT:-8100}"
MERCHANT_MCP_PORT="${UNIFIED_MERCHANT_MCP_PORT:-8101}"
CP_MCP_PORT="${UNIFIED_CP_MCP_PORT:-8102}"
MPP_MCP_PORT="${UNIFIED_MPP_MCP_PORT:-8103}"

if [ -f "$OPENCLAW_PID_FILE" ]; then
  echo "Stopping openclaw backend processes..."
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

echo "Freeing trigger + MCP ports..."
for port in 8091 8092 8093 8094 "$BUYER_MCP_PORT" "$MERCHANT_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT" "${UNIFIED_TRUSTED_SURFACE_PORT:-8104}" "${UNIFIED_MONITOR_SCHEDULER_PORT:-8105}"; do
  demo_kill_port "$port"
done
echo "Done. (op: ap2.unified.openclaw.stop)"
