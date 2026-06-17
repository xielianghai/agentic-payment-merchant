#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/dev-common.sh"

cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
exec npm run dev -- --port "${FRONTEND_PORT:-5273}" --strictPort
