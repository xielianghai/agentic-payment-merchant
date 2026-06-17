#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/dev-common.sh"

wait_for_mysql

cd "$ROOT/backend"
export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD API_PORT
export MYSQL_HOST="${MYSQL_HOST:-$DB_HOST}"
export MYSQL_PORT="${MYSQL_PORT:-$DB_PORT}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-$DB_NAME}"
export MYSQL_USER="${MYSQL_USER:-$DB_USER}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-$DB_PASSWORD}"

bash database/flyway/migrate.sh

PYTHON_BIN="$(resolve_python)"
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_PYTHON" -m pip install -U pip -q
"$VENV_PYTHON" -m pip install -r requirements.txt -q

exec "$VENV_DIR/bin/uvicorn" main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-9100}" --reload
