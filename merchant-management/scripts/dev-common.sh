#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS_DIR/.." && pwd)"
BACKEND_ENV_FILE="${BACKEND_ENV_FILE:-$ROOT/backend/.env}"

if [[ -f "$BACKEND_ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$BACKEND_ENV_FILE"
  set +a
fi

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-agentic_merchant_mgmt}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-12345678}"
API_PORT="${API_PORT:-9100}"
FRONTEND_PORT="${FRONTEND_PORT:-5273}"

wait_for_mysql() {
  echo "Waiting for MySQL at ${DB_HOST}:${DB_PORT}..."
  local i=0
  while [[ "$i" -lt 30 ]]; do
    if (echo >/dev/tcp/"$DB_HOST"/"$DB_PORT") 2>/dev/null; then
      echo "MySQL is reachable."
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  echo "ERROR: MySQL is not reachable at ${DB_HOST}:${DB_PORT}" >&2
  return 1
}

resolve_python() {
  for py in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      command -v "$py"
      return 0
    fi
  done
  echo "python"
}
