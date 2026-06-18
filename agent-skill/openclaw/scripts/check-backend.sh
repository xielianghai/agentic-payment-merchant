#!/usr/bin/env bash
# Verify HEG Flight + Agentic Payment Merchant backends for heg-flight skill.
set -eu

MERCHANT_HOME="${MERCHANT_HOME:-}"
if [ -z "$MERCHANT_HOME" ]; then
  SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  SEARCH_DIR="$SKILL_DIR"
  while [ "$SEARCH_DIR" != "/" ]; do
    if [ -f "$SEARCH_DIR/scripts/start-all.sh" ] && [ -d "$SEARCH_DIR/payment-stack" ]; then
      MERCHANT_HOME="$SEARCH_DIR"
      break
    fi
    SEARCH_DIR="$(dirname "$SEARCH_DIR")"
  done
fi

if [ ! -f "$MERCHANT_HOME/scripts/start-all.sh" ]; then
  echo "ERROR: set MERCHANT_HOME to the agentic-payment-merchant repository root" >&2
  exit 1
fi

missing=0
check_port() {
  local port="$1" label="$2"
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    echo "OK  $label (port $port)"
  else
    echo "FAIL $label (port $port)"
    missing=1
  fi
}

check_url() {
  local url="$1" label="$2"
  if curl -sf "$url" >/dev/null 2>&1; then
    echo "OK  $label ($url)"
  else
    echo "FAIL $label ($url)"
    missing=1
  fi
}

echo "MERCHANT_HOME=$MERCHANT_HOME"
echo ""

check_url "http://127.0.0.1:9000/health" "HEG Flight API"
check_url "http://127.0.0.1:9100/health" "Merchant Management API"
check_url "http://127.0.0.1:8200/health" "Adapter UCP"
check_port 8100 "Buyer MCP"
check_port 8102 "CP MCP"
check_port 8103 "MPP MCP"
check_port 8104 "Trusted Surface"
check_port 8105 "Monitor scheduler"

if [ "$missing" = "1" ]; then
  echo ""
  echo "Start stack:" >&2
  echo "  cd $MERCHANT_HOME/../heg_flight_mock && ./scripts/start-backend.sh" >&2
  echo "  cd $MERCHANT_HOME && ./scripts/start-all.sh" >&2
  echo "  MERCHANT_HOME=$MERCHANT_HOME <heg-flight-skill>/scripts/start-backend.sh" >&2
  exit 1
fi

echo ""
echo "HEG Flight backends look up."
