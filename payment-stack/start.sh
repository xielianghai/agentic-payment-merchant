#!/bin/bash
# ---------------------------------------------------------------------------
# Start AP2 Unified demo in the background.
#
# Usage:
#   ./start.sh              # daemon (logs in .logs/)
#   ./start.sh --foreground # block terminal, stream logs (like old run.sh)
#   AP2_LOG_TO_CONSOLE=1 ./start.sh --foreground
# ---------------------------------------------------------------------------

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init

DEMO_FOREGROUND=0
for arg in "$@"; do
  case "$arg" in
    --foreground|-f) DEMO_FOREGROUND=1 ;;
    --help|-h)
      echo "Usage: ./start.sh [--foreground]"
      echo "  --foreground  Stream logs here; Ctrl+C stops all services"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

if demo_is_running; then
  echo "AP2 Unified demo already running (pid file: $PID_FILE)." >&2
  echo "Run ./stop.sh first." >&2
  exit 1
fi

rm -f "$PID_FILE"
rm -rf "$TEMP_DB" "$LOG_DIR"
mkdir -p "$TEMP_DB" "$LOG_DIR"

echo "Syncing workspace dependencies..."
if ! (cd "$SAMPLES_ROOT" && uv sync --package ap2-samples --quiet); then
  echo "ERROR: uv sync failed — install deps from code/samples/python first." >&2
  exit 1
fi

echo "Verifying unified mandate tool bridge..."
(
  cd "$REPO_ROOT" &&
  "${UV_RUN_ARR[@]}" python "$SCRIPT_DIR/scripts/verify_unified_tools.py"
) || {
  echo "ERROR: verify_unified_tools.py failed — fix before starting demo." >&2
  exit 1
}

demo_install_web_client

DEMO_PIDS=()

demo_cleanup() {
  echo ""
  echo "Shutting down..."
  if [[ ${#DEMO_PIDS[@]} -gt 0 ]]; then
    kill -TERM "${DEMO_PIDS[@]}" 2>/dev/null || true
    sleep 1
    kill -KILL "${DEMO_PIDS[@]}" 2>/dev/null || true
    wait "${DEMO_PIDS[@]}" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Done."
}

if [ "$DEMO_FOREGROUND" = "1" ]; then
  trap demo_cleanup EXIT
fi

UNIFIED_MERCHANT="${UNIFIED_MERCHANT:-shoe}"
echo "Unified merchant profile (default): ${UNIFIED_MERCHANT}"
echo "Both merchants available — switch SuperShoe / Singapore Airlines in the web UI."

demo_check_heg_backend || echo "Warning: HEG backend not reachable; flight merchant may fail until you start it."

demo_kill_port "$MERCHANT_TRIGGER_PORT"
demo_start_service "merchant-trigger" "$ROLES_DIR/merchant_unified" "$MERCHANT_TRIGGER_PORT" \
  python trigger_server.py
sleep 0.5

demo_kill_port "$CP_TRIGGER_PORT"
demo_start_service "cp-trigger" "$ROLES_DIR/credentials_provider_unified" "$CP_TRIGGER_PORT" \
  python trigger_server.py
sleep 0.5

demo_kill_port "$MPP_TRIGGER_PORT"
demo_start_service "mpp-trigger" "$ROLES_DIR/merchant_payment_processor_unified" "$MPP_TRIGGER_PORT" \
  python trigger_server.py
echo "Waiting for MPP trigger..."
if ! demo_wait_for_mpp_trigger "$MPP_TRIGGER_PORT" 15; then
  echo "ERROR: MPP trigger did not become ready on port $MPP_TRIGGER_PORT." >&2
  exit 1
fi

demo_kill_port "$X402_PSP_TRIGGER_PORT"
demo_start_service "x402-psp-trigger" "$ROLES_DIR/merchant_payment_processor_unified" "$X402_PSP_TRIGGER_PORT" \
  python x402_trigger_server.py
sleep 0.5

TRUSTED_SURFACE_PORT="${UNIFIED_TRUSTED_SURFACE_PORT:-8104}"
export TS_BASE_URL="${TS_BASE_URL:-http://localhost:${TRUSTED_SURFACE_PORT}}"
demo_kill_port "$TRUSTED_SURFACE_PORT"
demo_start_service "trusted-surface" "$ROLES_DIR/trusted_surface_unified" "$TRUSTED_SURFACE_PORT" \
  python server.py
sleep 0.5

MONITOR_SCHEDULER_PORT="${UNIFIED_MONITOR_SCHEDULER_PORT:-8105}"
export MONITOR_SCHEDULER_BASE_URL="${MONITOR_SCHEDULER_BASE_URL:-http://localhost:${MONITOR_SCHEDULER_PORT}}"
export VITE_MONITOR_SCHEDULER_URL="${MONITOR_SCHEDULER_BASE_URL}"
export VITE_MONITOR_INTERVAL_MINUTES="${MONITOR_INTERVAL_MINUTES:-1}"
demo_kill_port "$MONITOR_SCHEDULER_PORT"
demo_start_service "monitor-scheduler" "$ROLES_DIR/monitor_scheduler_unified" "$MONITOR_SCHEDULER_PORT" \
  python server.py
echo "Waiting for monitor scheduler..."
if ! demo_wait_for_url "http://localhost:$MONITOR_SCHEDULER_PORT/health" 60; then
  echo "Monitor scheduler not ready; check $LOG_DIR/monitor-scheduler.log" >&2
fi

demo_kill_port "$AGENT_PORT"
demo_start_service "shopping-agent" "$ROLES_DIR/shopping_agent_unified" "$AGENT_PORT" \
  python run_server.py

echo "Waiting for agent..."
if ! demo_wait_for_url "http://localhost:$AGENT_PORT/a2a/shopping_agent/.well-known/agent-card.json" 30; then
  echo "Agent card not ready; checking /health and list-apps..."
  demo_wait_for_url "http://localhost:$AGENT_PORT/health" 30
  curl -s "http://localhost:$AGENT_PORT/list-apps" || true
  demo_wait_for_url "http://localhost:$AGENT_PORT/a2a/shopping_agent/.well-known/agent-card.json" 90
fi

demo_kill_port "$WEB_CLIENT_PORT"

echo "Starting web-client (port ${WEB_CLIENT_PORT})..."
if [ "${AP2_LOG_TO_CONSOLE}" = "1" ] && [ "$DEMO_FOREGROUND" = "1" ]; then
  (
    cd "$WEB_CLIENT_DIR" &&
    npm run dev -- --port "$WEB_CLIENT_PORT" --strictPort --host 127.0.0.1
  ) > >(
    tee "$LOG_DIR/web-client.log" | sed "s/^/[web-client] /"
  ) 2>&1 &
else
  (
    cd "$WEB_CLIENT_DIR" &&
    npm run dev -- --port "$WEB_CLIENT_PORT" --strictPort --host 127.0.0.1
  ) >>"$LOG_DIR/web-client.log" 2>&1 &
fi
demo_record_pid "$!"

echo "Waiting for web client..."
demo_wait_for_url "http://localhost:$WEB_CLIENT_PORT" 60

echo ""
echo "AP2 Unified demo is running. (op: ap2.unified.web)"
echo "  Default merchant: ${UNIFIED_MERCHANT} (switch in web UI header)"
echo "  Web UI:     http://localhost:$WEB_CLIENT_PORT"
echo "  Agent A2A:  http://localhost:$AGENT_PORT/a2a/shopping_agent"
echo "  Trusted Surface (H5): http://localhost:$TRUSTED_SURFACE_PORT/"
echo "  TS demo PIN (fallback): ${TS_PIN:-not set — passkey only}"
echo "  Monitor scheduler: http://localhost:$MONITOR_SCHEDULER_PORT/"
echo "  Shoe trigger: http://localhost:$MERCHANT_TRIGGER_PORT/trigger-price-drop"
echo "  HEG API:    ${HEG_FLIGHT_BACKEND_URL:-http://127.0.0.1:9000}"
echo "  Pids:       $PID_FILE"
echo "  Logs:       $LOG_DIR/"
echo ""
echo "Switch merchant in the web UI (SuperShoe / Singapore Airlines)."
echo ""
echo "HNP price-drop curl (SuperShoe, after mandate signed):"
echo "  curl -X POST \"http://localhost:$MERCHANT_TRIGGER_PORT/trigger-price-drop?item_id=<item_id>&price=<price>&stock=10\""
echo ""
echo "HNP monitor E2E smoke (register → trigger → purchase):"
echo "  uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py"
echo ""
echo "Flight sample prompts (select Singapore Airlines in UI):"
echo "  HP + card: Buy Singapore Airlines SIN to PVG economy June 10 for 1 adult now with card."
echo "  HNP: Book SIN to PVG economy June 10 for 1 adult, budget USD 600."
echo ""

if command -v open >/dev/null 2>&1; then
  open "http://localhost:$WEB_CLIENT_PORT"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$WEB_CLIENT_PORT"
fi

if [ "$DEMO_FOREGROUND" = "1" ]; then
  # shellcheck disable=SC2162
  while IFS= read -r pid; do
    [ -n "$pid" ] && DEMO_PIDS+=("$pid")
  done < "$PID_FILE"
  echo "Press Ctrl+C to stop all servers."
  wait
else
  echo "Stop with: ./stop.sh"
  echo "Tail logs:  tail -f $LOG_DIR/shopping-agent.log"
fi
