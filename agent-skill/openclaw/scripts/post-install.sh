#!/usr/bin/env bash
# Run after installing/copying the heg-flight skill.
set -eu

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MERCHANT_HOME="${MERCHANT_HOME:-}"
if [ -z "$MERCHANT_HOME" ]; then
  SEARCH_DIR="$SKILL_DIR"
  while [ "$SEARCH_DIR" != "/" ]; do
    if [ -f "$SEARCH_DIR/scripts/start-all.sh" ] && [ -d "$SEARCH_DIR/payment-stack" ]; then
      MERCHANT_HOME="$SEARCH_DIR"
      break
    fi
    SEARCH_DIR="$(dirname "$SEARCH_DIR")"
  done
fi

echo "HEG Flight skill installed at: $SKILL_DIR"
echo ""
echo "Next steps:"
echo "  1. export MERCHANT_HOME=${MERCHANT_HOME:-/path/to/agentic-payment-merchant}"
echo "  2. Start HEG + merchant stack:"
echo "       cd \$MERCHANT_HOME/../heg_flight_mock && ./scripts/start-backend.sh"
echo "       cd \$MERCHANT_HOME && ./scripts/start-all.sh"
echo "  3. Start buyer MCP (if ports 8100/8102/8103 are down):"
echo "       $SKILL_DIR/scripts/start-backend.sh"
echo "  4. Onboard HEG in Merchant Management → http://127.0.0.1:5273"
echo "  5. export MCPORTER_CONFIG=\"$SKILL_DIR/mcporter.json\""
echo "  6. Enable mcporter + heg-flight in your OpenClaw/QClaw config, then restart the gateway"
echo ""
echo "Verify: MERCHANT_HOME=\$MERCHANT_HOME $SKILL_DIR/scripts/check-backend.sh"
