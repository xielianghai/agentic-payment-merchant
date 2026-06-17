#!/usr/bin/env bash
# Run after: ./agent-skill/install-qclaw-skill.sh
set -eu

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MERCHANT_HOME="$(cd "$SKILL_DIR/../../.." && pwd)"

echo "HEG Flight skill installed at: $SKILL_DIR"
echo ""
echo "Next steps:"
echo "  1. export MERCHANT_HOME=$MERCHANT_HOME"
echo "  2. Start HEG + merchant stack:"
echo "       cd \$MERCHANT_HOME/../heg_flight_mock && ./scripts/start-backend.sh"
echo "       cd \$MERCHANT_HOME && ./scripts/start-all.sh"
echo "  3. Start buyer MCP (if ports 8100/8102/8103 are down):"
echo "       $SKILL_DIR/scripts/start-backend.sh"
echo "  4. Onboard HEG in Merchant Management → http://127.0.0.1:5273"
echo "  5. export MCPORTER_CONFIG=\"$SKILL_DIR/mcporter.json\""
echo "  6. Enable mcporter + heg-flight in ~/.qclaw/openclaw.json, restart QClaw"
echo ""
echo "Verify: MERCHANT_HOME=\$MERCHANT_HOME $SKILL_DIR/scripts/check-backend.sh"
