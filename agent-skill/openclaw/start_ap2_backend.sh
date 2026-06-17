#!/bin/bash
# ---------------------------------------------------------------------------
# Start AP2 mock backend for openclaw (triggers + HTTP MCP; no ADK agent / web UI).
#
# Usage:
#   ./openclaw/start_ap2_backend.sh
#   ./openclaw/stop_ap2_backend.sh
# ---------------------------------------------------------------------------

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init

# OTP step-up for Feishu Trusted Surface (legacy; H5 portal is default).
export AP2_TS_H5="${AP2_TS_H5:-1}"
export AP2_REQUIRE_OTP="${AP2_REQUIRE_OTP:-0}"
export TS_BASE_URL="${TS_BASE_URL:-http://localhost:8104}"
export TEMP_DB_DIR="${TEMP_DB_DIR:-$TEMP_DB}"
export AP2_OPENCLAW_HOOK_ENABLED="${AP2_OPENCLAW_HOOK_ENABLED:-1}"
export AP2_OPENCLAW_HOOK_URL="${AP2_OPENCLAW_HOOK_URL:-http://127.0.0.1:18789/hooks/agent}"
if [ -z "${AP2_OPENCLAW_HOOK_TOKEN:-}" ] && [ -f "$HOME/.openclaw/openclaw.json" ]; then
  AP2_OPENCLAW_HOOK_TOKEN="$(
    python3 -c "import json; print(json.load(open('$HOME/.openclaw/openclaw.json')).get('hooks',{}).get('token',''))" 2>/dev/null || true
  )"
fi
export AP2_OPENCLAW_HOOK_TOKEN

OPENCLAW_RUN_DIR="$SCRIPT_DIR/.run-openclaw"
OPENCLAW_PID_FILE="$OPENCLAW_RUN_DIR/pids"
BUYER_MCP_PORT="${UNIFIED_BUYER_MCP_PORT:-8100}"
MERCHANT_MCP_PORT="${UNIFIED_MERCHANT_MCP_PORT:-8101}"
CP_MCP_PORT="${UNIFIED_CP_MCP_PORT:-8102}"
MPP_MCP_PORT="${UNIFIED_MPP_MCP_PORT:-8103}"
TRUSTED_SURFACE_PORT="${UNIFIED_TRUSTED_SURFACE_PORT:-8104}"
MONITOR_SCHEDULER_PORT="${UNIFIED_MONITOR_SCHEDULER_PORT:-8105}"
MCP_PATH="${AP2_MCP_HTTP_PATH:-/mcp}"

if [ -f "$OPENCLAW_PID_FILE" ]; then
  running=0
  while IFS= read -r pid; do
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && running=1
  done < "$OPENCLAW_PID_FILE"
  if [ "$running" = "1" ]; then
    echo "AP2 openclaw backend already running (pid file: $OPENCLAW_PID_FILE)." >&2
    echo "Run ./openclaw/stop_ap2_backend.sh first." >&2
    exit 1
  fi
fi

rm -f "$OPENCLAW_PID_FILE"
rm -rf "$TEMP_DB" "$LOG_DIR"
mkdir -p "$TEMP_DB" "$LOG_DIR" "$OPENCLAW_RUN_DIR"

echo "Syncing workspace dependencies..."
(cd "$SAMPLES_ROOT" && uv sync --package ap2-samples --quiet)

if [ "${AP2_INSTALL_QUICK:-}" != "1" ]; then
  echo "Verifying unified mandate tool bridge..."
  (
    cd "$ROLES_DIR/shopping_agent_unified" &&
    "${UV_RUN_ARR[@]}" python "$SCRIPT_DIR/scripts/verify_unified_tools.py"
  ) || {
    echo "ERROR: verify_unified_tools.py failed." >&2
    exit 1
  }
else
  echo "Skipping verify (AP2_INSTALL_QUICK=1)."
fi

record_openclaw_pid() {
  echo "$1" >>"$OPENCLAW_PID_FILE"
}

openclaw_start_service() {
  local name="$1" dir="$2" port="$3"
  shift 3
  local log_file="$LOG_DIR/${name}.log"
  echo "Starting ${name} (port ${port})..."
  (cd "$dir" && "${UV_RUN_ARR[@]}" "$@") >>"$log_file" 2>&1 &
  record_openclaw_pid "$!"
}

start_mcp_http() {
  local name="$1" server_path="$2" port="$3"
  local log_file="$LOG_DIR/${name}-mcp-http.log"
  echo "Starting ${name} MCP HTTP (port ${port})..."
  (
    cd "$ROLES_DIR" &&
    "${UV_RUN_ARR[@]}" python http_mcp_launcher.py "$server_path" "$port" "$MCP_PATH"
  ) >>"$log_file" 2>&1 &
  record_openclaw_pid "$!"
}

# --- HTTP trigger servers (mock PSP / merchant callbacks) ---
demo_kill_port "$MERCHANT_TRIGGER_PORT"
openclaw_start_service "merchant-trigger" "$ROLES_DIR/merchant_unified" "$MERCHANT_TRIGGER_PORT" \
  python trigger_server.py
sleep 0.5

demo_kill_port "$CP_TRIGGER_PORT"
openclaw_start_service "cp-trigger" "$ROLES_DIR/credentials_provider_unified" "$CP_TRIGGER_PORT" \
  python trigger_server.py
sleep 0.5

demo_kill_port "$MPP_TRIGGER_PORT"
openclaw_start_service "mpp-trigger" "$ROLES_DIR/merchant_payment_processor_unified" "$MPP_TRIGGER_PORT" \
  python trigger_server.py
echo "Waiting for MPP trigger..."
demo_wait_for_mpp_trigger "$MPP_TRIGGER_PORT" 15

demo_kill_port "$X402_PSP_TRIGGER_PORT"
openclaw_start_service "x402-psp-trigger" "$ROLES_DIR/merchant_payment_processor_unified" "$X402_PSP_TRIGGER_PORT" \
  python x402_trigger_server.py
sleep 0.5

# --- Long-lived HTTP MCP servers ---
for port in "$BUYER_MCP_PORT" "$MERCHANT_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT"; do
  demo_kill_port "$port"
done

start_mcp_http "buyer" "$ROLES_DIR/buyer_mcp_unified/server.py" "$BUYER_MCP_PORT"
sleep 1
start_mcp_http "merchant" "$ROLES_DIR/merchant_router_unified/server.py" "$MERCHANT_MCP_PORT"
sleep 0.5
start_mcp_http "cp" "$ROLES_DIR/credentials_provider_unified/server.py" "$CP_MCP_PORT"
sleep 0.5
start_mcp_http "mpp" "$ROLES_DIR/merchant_payment_processor_unified/server.py" "$MPP_MCP_PORT"
sleep 1

demo_kill_port "$TRUSTED_SURFACE_PORT"
openclaw_start_service "trusted-surface" "$ROLES_DIR/trusted_surface_unified" "$TRUSTED_SURFACE_PORT" \
  python server.py
sleep 0.5

demo_kill_port "$MONITOR_SCHEDULER_PORT"
openclaw_start_service "monitor-scheduler" "$ROLES_DIR/monitor_scheduler_unified" "$MONITOR_SCHEDULER_PORT" \
  python server.py
sleep 0.5

echo "Waiting for MCP HTTP ports (streamable-http; plain GET returns 406)..."
for port in "$BUYER_MCP_PORT" "$MERCHANT_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT"; do
  ready=0
  i=0
  while [ "$i" -lt 90 ]; do
    if lsof -ti tcp:"${port}" >/dev/null 2>&1; then
      ready=1
      break
    fi
    i=$((i + 1))
    sleep 0.5
  done
  if [ "$ready" != "1" ]; then
    echo "ERROR: MCP port $port did not open — check $LOG_DIR/*-mcp-http.log" >&2
    exit 1
  fi
done

echo ""
echo "AP2 openclaw mock backend is running. (op: ap2.unified.openclaw)"
echo "  Buyer MCP:    http://127.0.0.1:${BUYER_MCP_PORT}${MCP_PATH}"
echo "  Merchant MCP: http://127.0.0.1:${MERCHANT_MCP_PORT}${MCP_PATH}"
echo "  CP MCP:       http://127.0.0.1:${CP_MCP_PORT}${MCP_PATH}"
echo "  MPP MCP:      http://127.0.0.1:${MPP_MCP_PORT}${MCP_PATH}"
echo "  Trusted Surface (H5): http://127.0.0.1:${TRUSTED_SURFACE_PORT}/"
echo "  Monitor scheduler:    http://127.0.0.1:${MONITOR_SCHEDULER_PORT}/"
echo "  Shoe trigger: http://127.0.0.1:${MERCHANT_TRIGGER_PORT}/trigger-price-drop"
echo "  Temp DB:      $TEMP_DB"
echo "  H5 TS:        AP2_TS_H5=$AP2_TS_H5  TS_BASE_URL=$TS_BASE_URL"
echo "  OTP step-up:  AP2_REQUIRE_OTP=$AP2_REQUIRE_OTP (legacy Feishu OTP path)"
echo "  Pids:         $OPENCLAW_PID_FILE"
echo "  Logs:         $LOG_DIR/"
echo ""
echo "mcporter config: $SCRIPT_DIR/openclaw/mcporter.json"
echo "Stop with: ./openclaw/stop_ap2_backend.sh"
echo ""
echo "HNP price-drop curl (after mandate signed):"
echo "  curl -X POST \"http://127.0.0.1:${MERCHANT_TRIGGER_PORT}/trigger-price-drop?item_id=<item_id>&price=199&stock=10\""
