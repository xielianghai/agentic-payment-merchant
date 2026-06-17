#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADAPTER_DIR="$ROOT/adapter"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT/.env"
  set +a
fi

export API_HOST="${ADAPTER_API_HOST:-127.0.0.1}"
export API_PORT="${ADAPTER_PORT:-8200}"
export TEMP_DB_DIR="${TEMP_DB_DIR:-$ROOT/payment-stack/.temp-db}"
export LOGS_DIR="${LOGS_DIR:-$ROOT/payment-stack/.logs}"
export no_proxy="127.0.0.1,localhost,0.0.0.0,::1,${no_proxy:-}"
export NO_PROXY="$no_proxy"
mkdir -p "$TEMP_DB_DIR" "$LOGS_DIR"

cd "$ADAPTER_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="$ADAPTER_DIR/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
"$VENV/bin/pip" install -U pip -q
"$VENV/bin/pip" install -r requirements.txt -q

exec "$VENV/bin/uvicorn" main:app --host "$API_HOST" --port "$API_PORT" --reload
