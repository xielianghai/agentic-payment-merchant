#!/usr/bin/env bash
# Start buyer/cp/mpp HTTP MCP for heg-flight (no merchant MCP — use Adapter).
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERCHANT_HOME="${MERCHANT_HOME:-}"
if [ -z "$MERCHANT_HOME" ]; then
  SEARCH_DIR="$SCRIPT_DIR"
  while [ "$SEARCH_DIR" != "/" ]; do
    if [ -f "$SEARCH_DIR/scripts/start-all.sh" ] && [ -d "$SEARCH_DIR/payment-stack" ]; then
      MERCHANT_HOME="$SEARCH_DIR"
      break
    fi
    SEARCH_DIR="$(dirname "$SEARCH_DIR")"
  done
fi
if [ -z "$MERCHANT_HOME" ] || [ ! -f "$MERCHANT_HOME/scripts/start-all.sh" ]; then
  echo "ERROR: set MERCHANT_HOME to the agentic-payment-merchant repository root" >&2
  exit 1
fi
PAYMENT_STACK="$MERCHANT_HOME/payment-stack"

# shellcheck disable=SC1091
source "$PAYMENT_STACK/scripts/demo_lib.sh"
demo_lib_init_minimal

if [ -f "$MERCHANT_HOME/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$MERCHANT_HOME/.env"
  set +a
fi

UV_RUN_ARR=(uv run --no-sync --package ap2-samples --project "$REPO_ROOT")
if [ -f "$REPO_ROOT/.env" ]; then
  UV_RUN_ARR+=(--env-file "$REPO_ROOT/.env")
fi

OPENCLAW_RUN_DIR="$PAYMENT_STACK/.run-qclaw-heg"
OPENCLAW_PID_FILE="$OPENCLAW_RUN_DIR/pids"
BUYER_MCP_PORT="${UNIFIED_BUYER_MCP_PORT:-8100}"
CP_MCP_PORT="${UNIFIED_CP_MCP_PORT:-8102}"
MPP_MCP_PORT="${UNIFIED_MPP_MCP_PORT:-8103}"
MCP_PATH="${AP2_MCP_HTTP_PATH:-/mcp}"

# Must match payment-stack/start.sh (Trusted Surface on :8104). Do not inherit
# AP2 unified demo TEMP_DB_DIR from the shell — that splits ts_sessions.json.
export TEMP_DB_DIR="$PAYMENT_STACK/.temp-db"
export AP2_TS_H5="${AP2_TS_H5:-1}"
export AP2_REQUIRE_OTP="${AP2_REQUIRE_OTP:-0}"
export TS_BASE_URL="${TS_BASE_URL:-http://localhost:${UNIFIED_TRUSTED_SURFACE_PORT:-8104}}"
mkdir -p "$TEMP_DB_DIR" "$LOG_DIR" "$OPENCLAW_RUN_DIR"

if [ -f "$OPENCLAW_PID_FILE" ]; then
  running=0
  while IFS= read -r pid; do
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && running=1
  done < "$OPENCLAW_PID_FILE"
  if [ "$running" = "1" ]; then
    echo "HEG Flight buyer MCP already running (pid file: $OPENCLAW_PID_FILE)." >&2
    exit 0
  fi
fi

rm -f "$OPENCLAW_PID_FILE"

echo "Syncing Python dependencies..."
(cd "$SAMPLES_ROOT" && uv sync --package ap2-samples --quiet) || {
  echo "ERROR: uv sync failed — set AP2_ROOT in $MERCHANT_HOME/.env" >&2
  exit 1
}

record_pid() {
  echo "$1" >>"$OPENCLAW_PID_FILE"
}

start_mcp_http() {
  local name="$1" server_path="$2" port="$3"
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    echo "Skip ${name} MCP — port ${port} already in use."
    return 0
  fi
  local log_file="$LOG_DIR/${name}-mcp-http.log"
  echo "Starting ${name} MCP HTTP (port ${port})..."
  (
    cd "$ROLES_DIR" &&
    "${UV_RUN_ARR[@]}" python http_mcp_launcher.py "$server_path" "$port" "$MCP_PATH"
  ) >>"$log_file" 2>&1 &
  record_pid "$!"
}

for port in "$BUYER_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT"; do
  if ! lsof -ti tcp:"$port" >/dev/null 2>&1; then
    demo_kill_port "$port"
  fi
done

start_mcp_http "buyer" "$ROLES_DIR/buyer_mcp_unified/server.py" "$BUYER_MCP_PORT"
sleep 1
start_mcp_http "cp" "$ROLES_DIR/credentials_provider_unified/server.py" "$CP_MCP_PORT"
sleep 0.5
start_mcp_http "mpp" "$ROLES_DIR/merchant_payment_processor_unified/server.py" "$MPP_MCP_PORT"
sleep 1

echo "Waiting for buyer MCP ports..."
for port in "$BUYER_MCP_PORT" "$CP_MCP_PORT" "$MPP_MCP_PORT"; do
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    echo "  OK  port $port"
  else
    echo "ERROR: port $port did not open — check $LOG_DIR/*-mcp-http.log" >&2
    exit 1
  fi
done

echo ""
echo "HEG Flight buyer MCP is running."
echo "  Buyer MCP: http://127.0.0.1:${BUYER_MCP_PORT}${MCP_PATH}"
echo "  CP MCP:    http://127.0.0.1:${CP_MCP_PORT}${MCP_PATH}"
echo "  MPP MCP:   http://127.0.0.1:${MPP_MCP_PORT}${MCP_PATH}"
echo "  Pids:      $OPENCLAW_PID_FILE"
echo "  Stop:      $SCRIPT_DIR/stop-backend.sh"
