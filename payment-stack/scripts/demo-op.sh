#!/bin/bash
# Resolve AP2 unified demo operation IDs (see references/demo-ops.md).
# Usage: demo-op <ID> [extra args for foreground, etc.]
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init_minimal

OP="${1:-}"
shift 2>/dev/null || true

list_ops() {
  cat <<'EOF'
Lifecycle:
  ap2.unified.web              Start web demo (background)
  ap2.unified.web.foreground   Start web demo (foreground, logs in terminal)
  ap2.unified.web.stop         Stop web demo
  ap2.unified.openclaw         Start openclaw MCP backend
  ap2.unified.openclaw.stop    Stop openclaw backend
  ap2.unified.smoke            Health check (web demo must be running)

Prerequisites:
  ap2.prereq.python            Sync ap2-samples Python workspace
  ap2.prereq.heg               Start HEG flight backend (sibling repo)

Docs: references/demo-ops.md
EOF
}

if [ -z "$OP" ] || [ "$OP" = '--help' ] || [ "$OP" = '-h' ] || [ "$OP" = 'help' ] || [ "$OP" = 'list' ]; then
  list_ops
  exit 0
fi

run_op() {
  case "$1" in
    ap2.unified.web)
      exec "$SCRIPT_DIR/start.sh" "$@"
      ;;
    ap2.unified.web.foreground)
      exec "$SCRIPT_DIR/start.sh" --foreground "$@"
      ;;
    ap2.unified.web.stop)
      exec "$SCRIPT_DIR/stop.sh"
      ;;
    ap2.unified.openclaw)
      exec "$SCRIPT_DIR/openclaw/start_ap2_backend.sh"
      ;;
    ap2.unified.openclaw.stop)
      exec "$SCRIPT_DIR/openclaw/stop_ap2_backend.sh"
      ;;
    ap2.unified.smoke)
      exec "$SCRIPT_DIR/scripts/smoke_check.sh"
      ;;
    ap2.prereq.python)
      echo "==> ap2.prereq.python"
      (cd "$SAMPLES_ROOT" && uv sync --package ap2-samples)
      echo "OK (ap2.prereq.python)"
      ;;
    ap2.prereq.heg)
      local heg="${HEG_FLIGHT_REPO:-$REPO_ROOT/../heg_flight_mock}"
      if [ ! -d "$heg" ]; then
        echo "ERROR: HEG repo not found at $heg (set HEG_FLIGHT_REPO)" >&2
        exit 1
      fi
      echo "==> ap2.prereq.heg ($heg)"
      if [ -x "$heg/scripts/start-backend.sh" ]; then
        exec "$heg/scripts/start-backend.sh"
      fi
      echo "ERROR: missing $heg/scripts/start-backend.sh" >&2
      exit 1
      ;;
    ap2.cfg.merchant.flight)
      echo "Set before ap2.unified.web:"
      echo "  export UNIFIED_MERCHANT=flight"
      echo "  export VITE_MERCHANT_PROFILE=flight"
      ;;
    ap2.cfg.merchant.shoe)
      echo "Set before ap2.unified.web:"
      echo "  export UNIFIED_MERCHANT=shoe"
      echo "  export VITE_MERCHANT_PROFILE=shoe"
      ;;
    ap2.ui.web)
      echo "http://localhost:${WEB_CLIENT_PORT}"
      ;;
    ap2.ui.heg-admin)
      echo "http://localhost:5173"
      ;;
    ap2.flow.hnp.drop)
      echo "HTTP POST merchant trigger :${MERCHANT_TRIGGER_PORT}/trigger-price-drop"
      echo "  Query: item_id (from mandate), price, stock"
      echo "  Example item_id: supershoe_limited_edition_gold_sneaker_womens_9_0"
      ;;
    ap2.flow.hp.confirm)
      echo "Use web UI Confirm & pay after immediate_checkout_request"
      ;;
    ap2.flow.flight.hnp)
      echo "Flight HNP: no shoe trigger; adjust HEG fare or user price_cap in chat"
      ;;
    *)
      echo "Unknown op: $1" >&2
      echo "Run: demo-op --help" >&2
      exit 1
      ;;
  esac
}

echo "==> $OP"
run_op "$OP" "$@"
