#!/bin/bash
# Shared helpers for AP2 Unified demo (start.sh / stop.sh / run.sh).

# Resolved once when this file is sourced (BASH_SOURCE[0] == demo_lib.sh).
_DEMO_LIB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

AGENT_PORT=8090
MERCHANT_TRIGGER_PORT=8091
CP_TRIGGER_PORT=8092
MPP_TRIGGER_PORT=8093
X402_PSP_TRIGGER_PORT=8094
MONITOR_SCHEDULER_PORT=8105
WEB_CLIENT_PORT=5183

demo_lib_init_minimal() {
  if [ -n "${DEMO_LIB_MINIMAL_INITIALIZED:-}" ]; then
    return 0
  fi
  DEMO_LIB_MINIMAL_INITIALIZED=1

  readonly SCRIPT_DIR="$_DEMO_LIB_ROOT"
  readonly DEMO_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  if [[ -n "${AP2_ROOT:-}" ]]; then
    readonly REPO_ROOT="$(cd "$AP2_ROOT" && pwd)"
  else
    readonly REPO_ROOT="$(cd "$DEMO_REPO_ROOT/../AP2" && pwd)"
  fi
  readonly LOG_DIR="$SCRIPT_DIR/.logs"
  readonly RUN_DIR="$SCRIPT_DIR/.run"
  readonly PID_FILE="$RUN_DIR/pids"
  readonly TEMP_DB="$SCRIPT_DIR/.temp-db"
  readonly ROLES_DIR="$SCRIPT_DIR"
  readonly SAMPLES_ROOT="$REPO_ROOT/code/samples/python"
  readonly WEB_CLIENT_DIR="${WEB_CLIENT_DIR:-$DEMO_REPO_ROOT/web-chat-client}"

  mkdir -p "$LOG_DIR" "$RUN_DIR"
}

demo_ensure_uv_deps() {
  if [[ ! -d "$REPO_ROOT/code/samples/python" ]]; then
    echo "ERROR: AP2 not found at $REPO_ROOT" >&2
    echo "Set AP2_ROOT in $DEMO_REPO_ROOT/.env (e.g. AP2_ROOT=/path/to/payment/AP2)" >&2
    exit 1
  fi
  local py="${REPO_ROOT}/.venv/bin/python"
  if [ -x "$py" ] && "$py" -c "import google.adk" 2>/dev/null; then
    return 0
  fi
  echo "Syncing Python dependencies (ap2-samples)..."
  (cd "$REPO_ROOT" && uv sync --package ap2-samples) || {
    echo "ERROR: uv sync failed. Check network access to PyPI." >&2
    exit 1
  }
}

demo_install_web_client() {
  local wc="${WEB_CLIENT_DIR}"
  if [ -f "${wc}/node_modules/vite/package.json" ]; then
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is required for the unified web UI (Node.js 18+)." >&2
    exit 1
  fi
  if [ ! -f "${wc}/package-lock.json" ]; then
    echo "ERROR: ${wc}/package-lock.json is missing." >&2
    exit 1
  fi

  echo "Installing web-client dependencies (npm ci)..."
  local attempt registry
  for registry in "${NPM_CONFIG_REGISTRY:-}" "https://registry.npmjs.org" "https://registry.npmmirror.com"; do
    for attempt in 1 2 3; do
      if [ -n "$registry" ]; then
        echo "  npm ci attempt ${attempt}/3 (registry=${registry})"
        if (cd "$wc" && npm ci --no-fund --no-audit --registry "$registry"); then
          return 0
        fi
      else
        echo "  npm ci attempt ${attempt}/3 (default registry)"
        if (cd "$wc" && npm ci --no-fund --no-audit); then
          return 0
        fi
      fi
      sleep 2
    done
  done
  echo "ERROR: npm ci failed after retries. Check network or set NPM_CONFIG_REGISTRY." >&2
  echo "  Log: ls -t ~/.npm/_logs/*-debug-0.log | head -1" >&2
  exit 1
}

demo_all_ports() {
  echo "$MERCHANT_TRIGGER_PORT"
  echo "$CP_TRIGGER_PORT"
  echo "$MPP_TRIGGER_PORT"
  echo "$X402_PSP_TRIGGER_PORT"
  echo "$AGENT_PORT"
  echo "${UNIFIED_MONITOR_SCHEDULER_PORT:-$MONITOR_SCHEDULER_PORT}"
  echo "$WEB_CLIENT_PORT"
}

demo_build_uv_run_arr() {
  local ap2_env="${REPO_ROOT}/.env"
  local merchant_env="${DEMO_REPO_ROOT}/.env"
  local v2_env="$SAMPLES_ROOT/src/roles/shopping_agent_v2/.env"

  UV_RUN_ARR=(uv run --no-sync --package ap2-samples --project "$REPO_ROOT")
  if [ -f "$ap2_env" ]; then
    UV_RUN_ARR+=(--env-file "$ap2_env")
  fi
  if [ -f "$v2_env" ]; then
    UV_RUN_ARR+=(--env-file "$v2_env")
  fi
  # Merchant repo .env wins over AP2/.env (e.g. AP2_DISABLE_VI).
  if [ -f "$merchant_env" ]; then
    UV_RUN_ARR+=(--env-file "$merchant_env")
  fi
}

demo_require_llm_keys() {
  LLM_PROVIDER=$(printf "%s" "${LLM_PROVIDER:-google}" | tr '[:upper:]' '[:lower:]')
  USE_VERTEXAI=$(printf "%s" "${GOOGLE_GENAI_USE_VERTEXAI:-}" | tr '[:upper:]' '[:lower:]')
  if [ "${LLM_PROVIDER}" = "deepseek" ]; then
    if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
      echo "Please set DEEPSEEK_API_KEY when LLM_PROVIDER=deepseek." >&2
      exit 1
    fi
  elif [ -z "${GOOGLE_API_KEY:-}" ] && [ "${USE_VERTEXAI}" != "true" ]; then
    echo "Please set GOOGLE_API_KEY, or set LLM_PROVIDER=deepseek with DEEPSEEK_API_KEY." >&2
    exit 1
  fi
}

demo_lib_init() {
  if [ -n "${DEMO_LIB_INITIALIZED:-}" ]; then
    return 0
  fi
  DEMO_LIB_INITIALIZED=1

  demo_lib_init_minimal

  if [ -f "$DEMO_REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$DEMO_REPO_ROOT/.env"
    set +a
  fi

  if [ -f "$SAMPLES_ROOT/src/roles/shopping_agent_v2/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SAMPLES_ROOT/src/roles/shopping_agent_v2/.env"
    set +a
  fi

  demo_require_llm_keys
  demo_ensure_uv_deps

  demo_build_uv_run_arr

  export TEMP_DB_DIR="$TEMP_DB"
  export LOGS_DIR="$LOG_DIR"
  export MERCHANT_TRIGGER_STATE_PATH="$TEMP_DB/merchant_trigger_state.json"
  export AP2_TOKEN_STORE_PATH="$TEMP_DB/ap2_token_store.json"
  export MERCHANT_INVENTORY_PATH="$TEMP_DB/merchant_inventory.json"
  export AGENT_PUBLIC_KEY_PATH="$TEMP_DB/agent_signing_key.pub"
  export AGENT_PROVIDER_PUBLIC_KEY_PATH="$TEMP_DB/agent_provider_signing_key.pub"
  export MERCHANT_SIGNING_KEY_PATH="$TEMP_DB/merchant_signing_key.pem"
  export USER_SIGNING_KEY_PATH="$TEMP_DB/user_signing_key.pem"
  export USER_SIGNING_PUB_PATH="$TEMP_DB/user_signing_key.pub"

  export UNIFIED_MERCHANT="${UNIFIED_MERCHANT:-flight}"
  export HEG_FLIGHT_BACKEND_URL="${HEG_FLIGHT_BACKEND_URL:-http://127.0.0.1:9000}"
  export HEG_FLIGHT_MCP_SERVER="${HEG_FLIGHT_MCP_SERVER:-$DEMO_REPO_ROOT/../heg_flight_mock/mcp/server.py}"
  export ADAPTER_BASE_URL="${ADAPTER_BASE_URL:-http://127.0.0.1:8200}"
  export MERCHANT_MGMT_API="${MERCHANT_MGMT_API:-http://127.0.0.1:9100}"
  export ADAPTER_MCP_SERVER="${ADAPTER_MCP_SERVER:-$DEMO_REPO_ROOT/adapter/mcp/server.py}"
  export VITE_MERCHANT_PROFILE="${UNIFIED_MERCHANT}"

  export UNIFIED_AGENT_PORT="$AGENT_PORT"
  export UNIFIED_MERCHANT_TRIGGER_PORT="$MERCHANT_TRIGGER_PORT"
  export UNIFIED_CP_TRIGGER_PORT="$CP_TRIGGER_PORT"
  export UNIFIED_MPP_TRIGGER_PORT="$MPP_TRIGGER_PORT"
  export UNIFIED_X402_PSP_TRIGGER_PORT="$X402_PSP_TRIGGER_PORT"
  export VITE_MERCHANT_TRIGGER_URL="http://localhost:${MERCHANT_TRIGGER_PORT}"
  export MONITOR_INTERVAL_MINUTES="${MONITOR_INTERVAL_MINUTES:-1}"
  export VITE_MONITOR_INTERVAL_MINUTES="${MONITOR_INTERVAL_MINUTES}"
  # Demo PIN fallback when passkey picker is blocked or awkward (override in env).
  export TS_PIN="${TS_PIN:-123456}"
  export TS_SHOW_DEMO_PIN="${TS_SHOW_DEMO_PIN:-1}"
  export TS_AUTHENTICATOR="${TS_AUTHENTICATOR:-platform}"

  # Inter-service calls are all loopback (agent ↔ MCP ↔ triggers). A system /
  # env HTTP proxy (e.g. Clash/Surge on 127.0.0.1) otherwise intercepts these
  # and returns 502, so force loopback to bypass any proxy for every service.
  local _loopback_no_proxy="127.0.0.1,localhost,0.0.0.0,::1"
  if [ -n "${no_proxy:-}" ]; then
    export no_proxy="${_loopback_no_proxy},${no_proxy}"
  else
    export no_proxy="${_loopback_no_proxy}"
  fi
  if [ -n "${NO_PROXY:-}" ]; then
    export NO_PROXY="${_loopback_no_proxy},${NO_PROXY}"
  else
    export NO_PROXY="${_loopback_no_proxy}"
  fi

  export PYTHONPATH="${SAMPLES_ROOT}/src:${ROLES_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

  AP2_LOG_TO_CONSOLE="${AP2_LOG_TO_CONSOLE:-1}"
}

demo_kill_port() {
  local port="$1"
  local pid
  pid=$(lsof -ti tcp:"${port}" 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "Killing process on port $port (pid $pid)"
    kill -9 $pid 2>/dev/null || true
  fi
}

demo_wait_for_url() {
  local url="$1"
  local timeout="${2:-30}"
  local attempts=$(( timeout * 2 ))
  for (( i = 1; i <= attempts; i++ )); do
    if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q 200; then
      return 0
    fi
    sleep 0.5
  done
  echo "ERROR: Timed out waiting for $url" >&2
  return 1
}

demo_wait_for_mpp_trigger() {
  local port="$1"
  local timeout="${2:-15}"
  local attempts=$(( timeout * 2 ))
  local response
  for (( i = 1; i <= attempts; i++ )); do
    response=$(curl -s -X POST "http://127.0.0.1:${port}/initiate-payment" \
      -H "Content-Type: application/json" \
      -d '{"payment_token":"startup_probe","checkout_jwt_hash":"startup_probe","open_checkout_hash":"startup_probe"}' \
      2>/dev/null || true)
    if [[ "$response" == *'"error": "token_not_found"'* ]]; then
      return 0
    fi
    sleep 0.5
  done
  echo "ERROR: Timed out waiting for unified MPP trigger on port $port" >&2
  return 1
}

demo_check_heg_backend() {
  local url="${HEG_FLIGHT_BACKEND_URL:-http://127.0.0.1:9000}/health"
  echo "Checking HEG flight backend at $url ..."
  if demo_wait_for_url "$url" 10; then
    echo "HEG flight backend is healthy."
    return 0
  fi
  echo ""
  echo "ERROR: HEG flight backend is not reachable at $url" >&2
  echo "Start it separately before running flight mode:" >&2
  echo "  cd /path/to/heg_flight_mock && ./scripts/start-backend.sh" >&2
  echo ""
  return 1
}

demo_is_running() {
  if [ ! -f "$PID_FILE" ]; then
    return 1
  fi
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  done < "$PID_FILE"
  return 1
}

demo_record_pid() {
  local pid="$1"
  echo "$pid" >> "$PID_FILE"
}

demo_start_service() {
  local name="$1" dir="$2" port="$3"
  shift 3
  local log_file="$LOG_DIR/${name}.log"
  echo "Starting ${name} (port ${port})..."
  if [ "${AP2_LOG_TO_CONSOLE}" = "1" ] && [ "${DEMO_FOREGROUND:-0}" = "1" ]; then
    (
      cd "$dir" && "${UV_RUN_ARR[@]}" "$@"
    ) > >(
      tee "$log_file" | sed "s/^/[${name}] /"
    ) 2>&1 &
  else
    (cd "$dir" && "${UV_RUN_ARR[@]}" "$@") >>"$log_file" 2>&1 &
  fi
  demo_record_pid "$!"
}

demo_stop_all() {
  demo_lib_init_minimal

  if [ -f "$PID_FILE" ]; then
    echo "Stopping recorded processes..."
    # shellcheck disable=SC2162
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      kill -TERM "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    sleep 1
    # shellcheck disable=SC2162
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      kill -KILL "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  else
    echo "No pid file at $PID_FILE"
  fi

  echo "Ensuring demo ports are free..."
  while IFS= read -r port; do
    [ -n "$port" ] || continue
    demo_kill_port "$port"
  done < <(demo_all_ports)
  echo "Done. (op: ap2.unified.web.stop)"
}
