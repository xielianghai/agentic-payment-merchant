#!/usr/bin/env bash
# Quick UCP + AP2 bridge smoke test (no full AP2 mandate required for attach/finalize)
set -euo pipefail

ADAPTER="${ADAPTER_BASE_URL:-http://127.0.0.1:8200}"

echo "=== UCP+AP2 Bridge Smoke ==="

# 1. Catalog
ITEM=$(curl -sf -X POST "$ADAPTER/catalog/search" \
  -H 'Content-Type: application/json' \
  -d '{"query":"SIN to PVG 2026-06-10 economy 1 adult"}' \
  | python3 -c "import sys,json; m=json.load(sys.stdin)['matches'][0]; print(m['item_id'])")
echo "OK  catalog search → item_id=$ITEM"

# 2. Cart
CART_JSON=$(curl -sf -X POST "$ADAPTER/carts" \
  -H 'Content-Type: application/json' \
  -d "{\"item_id\":\"$ITEM\",\"qty\":1}")
ISSUE=$(echo "$CART_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['issue_id'])")
echo "OK  cart → issue_id=$ISSUE"

# 3. Checkout session
CHK_JSON=$(curl -sf -X POST "$ADAPTER/checkout-sessions" \
  -H 'Content-Type: application/json' \
  -d "{\"cart_id\":\"$ISSUE\"}")
CHK_ID=$(echo "$CHK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "OK  checkout session → id=$CHK_ID"

# 4. Attach mock AP2 mandate
ATTACH=$(curl -sf -X POST "$ADAPTER/checkout-sessions/$CHK_ID/ap2-mandate" \
  -H 'Content-Type: application/json' \
  -d '{"checkout_jwt":"eyJ.mock","checkout_jwt_hash":"mockhash123"}')
echo "$ATTACH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ap2_mandate'); print('OK  ap2_mandate attached')"

# 5. Finalize (sync only, no HEG pay)
FIN=$(curl -sf -X POST "$ADAPTER/checkout-sessions/$CHK_ID/finalize" \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"TEST-ORD-001","checkout_receipt":"mock-receipt"}')
echo "$FIN" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='completed'; print('OK  finalize → completed')"

echo ""
echo "UCP+AP2 bridge smoke passed."
