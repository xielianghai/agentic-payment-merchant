#!/bin/bash
# DEPRECATED: Backend scheduler on :8105 runs ticks and purchase automatically.
# This script was for manual/OpenClaw-cron agent ticks.
#
# One price-monitor tick: status → check_product → check_constraints → complete tick.
# Usage: ./scripts/monitor_price_tick.sh <session_id>
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init

SESSION_ID="${1:-}"
if [ -z "$SESSION_ID" ]; then
  echo "Usage: $0 <session_id>" >&2
  exit 1
fi

export MCPORTER_CONFIG="${MCPORTER_CONFIG:-$SCRIPT_DIR/openclaw/mcporter.json}"
MCPORTER=(mcporter)

# Exit codes: 0 tick recorded (keep looping) | 2 not due/skip | 3 STOP loop.
stop_cron() {
  "$SCRIPT_DIR/scripts/monitor_cron.sh" stop "$SESSION_ID" >/dev/null 2>&1 || true
}

STATUS="$("${MCPORTER[@]}" call ap2-buyer.get_price_monitor_status_tool \
  session_id="$SESSION_ID" --output json)"

if echo "$STATUS" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('should_stop') else 1)" 2>/dev/null; then
  echo "$STATUS"
  stop_cron
  echo "MONITOR_STOP: monitor already stopped — stop the loop." >&2
  exit 3
fi
if ! echo "$STATUS" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('due') else 1)" 2>/dev/null; then
  echo "$STATUS"
  echo "Monitor not due — skip tick." >&2
  exit 2
fi

ITEM_ID="$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('item_id',''))")"
PRICE_CAP="$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('price_cap',''))")"
CURRENCY="$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('currency','USD'))")"

PRODUCT="$("${MCPORTER[@]}" call ap2-merchant.check_product \
  item_id="$ITEM_ID" constraint_price_cap="$PRICE_CAP" --output json)"
echo "$PRODUCT"

NOT_FOUND="$(echo "$PRODUCT" | python3 -c "
import json,sys
p=json.load(sys.stdin)
err=str(p.get('error','')) + ' ' + str(p.get('message',''))
nf = ('error' in p) or ('not found' in err.lower()) or ('not_found' in err.lower())
print('true' if nf else 'false')
")"
PRICE="$(echo "$PRODUCT" | python3 -c "
import json,sys
p=json.load(sys.stdin)
print(p.get('price', p.get('current_price', 0)) or 0)
")"
AVAILABLE="$(echo "$PRODUCT" | python3 -c "
import json,sys
p=json.load(sys.stdin)
a=p.get('available', p.get('in_stock', True))
print('true' if a in (True, 'true', 1, '1') else 'false')
")"

if [ "$NOT_FOUND" = "true" ]; then
  RESULT="$("${MCPORTER[@]}" call ap2-buyer.complete_price_monitor_tick_tool \
    session_id="$SESSION_ID" \
    current_price=0 available=false meets_constraints=false \
    not_found=true message="Item not found in merchant inventory." \
    --output json)"
  echo "$RESULT"
  stop_cron
  echo "MONITOR_STOP: item not found — stop the loop." >&2
  exit 3
fi

CONSTRAINTS="$("${MCPORTER[@]}" call ap2-buyer.check_constraints \
  session_id="$SESSION_ID" price="$PRICE" currency="$CURRENCY" available="$AVAILABLE" --output json)"
echo "$CONSTRAINTS"

MEETS="$(echo "$CONSTRAINTS" | python3 -c "import json,sys; print(str(json.load(sys.stdin).get('meets_constraints', False)).lower())")"
MSG="$(echo "$CONSTRAINTS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('message',''))")"

RESULT="$("${MCPORTER[@]}" call ap2-buyer.complete_price_monitor_tick_tool \
  session_id="$SESSION_ID" \
  current_price="$PRICE" \
  available="$AVAILABLE" \
  meets_constraints="$MEETS" \
  message="$MSG" \
  --output json)"
echo "$RESULT"

if echo "$RESULT" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('should_stop') else 1)" 2>/dev/null; then
  stop_cron
  echo "MONITOR_STOP: terminal condition (constraints met / cap) — stop the loop." >&2
  exit 3
fi
exit 0
