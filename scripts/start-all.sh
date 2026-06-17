#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=dev-common.sh
source "$ROOT/scripts/dev-common.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT/.env"
  set +a
fi

export AP2_ROOT="${AP2_ROOT:-$ROOT/../AP2}"
export no_proxy="127.0.0.1,localhost,0.0.0.0,::1,${no_proxy:-}"
export NO_PROXY="$no_proxy"

echo "=== Agentic Payment Merchant Demo ==="
echo ""
echo "Prerequisites:"
echo "  1. MySQL running on ${DB_HOST:-127.0.0.1}:${DB_PORT:-3306}"
echo "  2. HEG Flight backend: cd ../heg_flight_mock && ./scripts/start-backend.sh"
echo "  3. Set DEEPSEEK_API_KEY in $ROOT/.env"
echo "  AP2_ROOT=${AP2_ROOT}"
echo ""

if [[ ! -d "$AP2_ROOT/code/samples/python" ]]; then
  echo "ERROR: AP2 not found at $AP2_ROOT" >&2
  echo "Set AP2_ROOT in .env to your AP2 checkout path." >&2
  exit 1
fi

echo "Stopping any previously running demo services..."
kill_demo_ports
sleep 1

# Merchant Management backend
echo "[1/5] Starting Merchant Management backend..."
mkdir -p "$ROOT/.logs"
nohup "$ROOT/merchant-management/scripts/start-backend.sh" >>"$ROOT/.logs/mm-backend.log" 2>&1 &
MM_BACKEND_PID=$!
if ! wait_for_url "http://127.0.0.1:${API_PORT:-9100}/health" 30; then
  echo "ERROR: Merchant Management backend failed to start on port ${API_PORT:-9100}" >&2
  echo "See $ROOT/.logs/mm-backend.log" >&2
  exit 1
fi

# Merchant Management frontend
echo "[2/5] Starting Merchant Management frontend..."
nohup "$ROOT/merchant-management/scripts/start-frontend.sh" >>"$ROOT/.logs/mm-frontend.log" 2>&1 &
MM_FRONTEND_PID=$!
sleep 2

# Adapter
echo "[3/5] Starting Adapter (UCP facade)..."
nohup "$ROOT/scripts/start-adapter.sh" >>"$ROOT/.logs/adapter.log" 2>&1 &
ADAPTER_PID=$!
if ! wait_for_url "http://127.0.0.1:${ADAPTER_PORT:-8200}/health" 30; then
  echo "ERROR: Adapter failed to start on port ${ADAPTER_PORT:-8200}" >&2
  echo "See $ROOT/.logs/adapter.log" >&2
  exit 1
fi

# Payment stack
echo "[4/5] Starting Payment stack..."
nohup bash -c "cd \"$ROOT/payment-stack\" && ./start.sh" >>"$ROOT/.logs/payment-stack.log" 2>&1 &
PAYMENT_PID=$!
sleep 12

echo "=== Demo URLs ==="
echo "  Merchant Management: http://127.0.0.1:5273  (or http://localhost:5273)"
echo "  Adapter UCP profile: http://127.0.0.1:8200/.well-known/ucp"
echo "  Web Chat Client:     http://127.0.0.1:5183"
echo "  Shopping Agent A2A:  http://127.0.0.1:8090/a2a/shopping_agent"
echo "  Trusted Surface:     http://127.0.0.1:8104"
echo ""
if ! curl -sf "http://127.0.0.1:8090/a2a/shopping_agent/.well-known/agent-card.json" >/dev/null 2>&1; then
  echo "NOTE: Payment stack (5183/8090/8104) may still be starting — wait ~30s or check payment-stack/.logs/"
fi
echo "Steps:"
echo "  1. Open Merchant Management → Onboard HEG Flight"
echo "  2. Open Web Chat → Buy Singapore Airlines SIN→PVG flight"
echo ""
echo "PIDs: MM=$MM_BACKEND_PID FE=$MM_FRONTEND_PID ADAPTER=$ADAPTER_PID PAYMENT=$PAYMENT_PID"
echo "Stop: ./scripts/stop-all.sh"
