#!/bin/bash
# Smoke test openclaw MCP stack via mcporter (backend must be running).
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MCPORTER_CONFIG="${MCPORTER_CONFIG:-$SCRIPT_DIR/openclaw/mcporter.json}"
TS_PORT="${UNIFIED_TRUSTED_SURFACE_PORT:-8104}"

if ! command -v npx >/dev/null 2>&1; then
  echo "ERROR: npx required" >&2
  exit 1
fi

MCPORTER=(npx -y mcporter@latest)

for port in 8100 8101 8102 8103 8105 "$TS_PORT"; do
  if ! lsof -ti tcp:"$port" >/dev/null 2>&1; then
    echo "ERROR: port $port not listening — run ./openclaw/start_ap2_backend.sh" >&2
    exit 1
  fi
done

echo "Monitor scheduler health..."
curl -sf "http://127.0.0.1:${UNIFIED_MONITOR_SCHEDULER_PORT:-8105}/health" | grep -q '"status": "ok"'

echo "Listing ap2-buyer tools..."
"${MCPORTER[@]}" list ap2-buyer --schema >/dev/null

SESSION="smoke-$(date +%s)"
echo "Session: $SESSION"

echo "set_ap2_session_config (hnp + card)..."
"${MCPORTER[@]}" call ap2-buyer.set_ap2_session_config_tool \
  session_id="$SESSION" presence_mode=hnp payment_method=card merchant=shoe --output json \
  | grep -q '"status": "ok"'

echo "create_trusted_surface_session..."
TS_JSON="$("${MCPORTER[@]}" call ap2-buyer.create_trusted_surface_session \
  session_id="$SESSION" price_cap=200 payment_method=card presence_mode=hnp \
  item_id=smoke_openclaw_item_0 item_name="Smoke Shoe" --output json)"
echo "$TS_JSON" | grep -q '"portal_url"'
REF="$(echo "$TS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['ref'])")"

echo "POST /ts/approve (ref=$REF)..."
curl -sf -X POST "http://127.0.0.1:${TS_PORT}/ts/approve" \
  -H 'Content-Type: application/json' \
  -d "{\"ref\":\"$REF\"}" | grep -q '"status": "ok"'

echo "get_trusted_surface_status..."
"${MCPORTER[@]}" call ap2-buyer.get_trusted_surface_status \
  ref="$REF" --output json | grep -q '"status": "signed"'

echo "assemble_and_sign_mandates..."
ASSEMBLE_ARGS="$(python3 -c "import json; print(json.dumps({'session_id':'$SESSION','mandate_request':json.dumps({'item_id':'smoke_openclaw_item_0','item_name':'Smoke','price_cap':200,'qty':1})}))")"
"${MCPORTER[@]}" call ap2-buyer.assemble_and_sign_mandates \
  --args "$ASSEMBLE_ARGS" \
  --output json | grep -q open_checkout_mandate

echo "ap2-merchant.check_product..."
"${MCPORTER[@]}" call ap2-merchant.check_product \
  item_id=smoke_openclaw_item_0 constraint_price_cap=200 --output json | grep -q item_id

echo "OK  openclaw MCP smoke passed (buyer + merchant + H5 Trusted Surface)."
