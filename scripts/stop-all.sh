#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=dev-common.sh
source "$ROOT/scripts/dev-common.sh"

echo "Stopping payment stack..."
if [[ -f "$ROOT/payment-stack/stop.sh" ]]; then
  (cd "$ROOT/payment-stack" && ./stop.sh) || true
fi

kill_demo_ports

echo "Done."
