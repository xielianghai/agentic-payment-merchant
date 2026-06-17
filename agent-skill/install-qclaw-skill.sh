#!/usr/bin/env bash
# Install / refresh heg-flight skill into QClaw (~/.qclaw/skills/heg-flight).
# Similar to payment-stack/scripts/reinstall_ap2_skill.sh for ap2-checkout.
set -eu

AGENT_SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERCHANT_HOME="$(cd "$AGENT_SKILL_DIR/.." && pwd)"
SRC_SKILL="$AGENT_SKILL_DIR/qclaw/heg-flight"

QCLAW_SKILL="${QCLAW_SKILL_DIR:-$HOME/.qclaw/skills/heg-flight}"
QCLAW_CONFIG="${QCLAW_CONFIG:-$HOME/.qclaw/openclaw.json}"

ADAPTER_MCP="$MERCHANT_HOME/adapter/mcp/server.py"
TEMP_DB_DIR="${TEMP_DB_DIR:-$MERCHANT_HOME/payment-stack/.temp-db}"

if [ ! -f "$SRC_SKILL/SKILL.md" ]; then
  echo "ERROR: missing $SRC_SKILL/SKILL.md" >&2
  exit 1
fi

if [ ! -f "$ADAPTER_MCP" ]; then
  echo "ERROR: missing adapter MCP at $ADAPTER_MCP" >&2
  exit 1
fi

# Load .env for HEG / adapter URLs when present.
if [ -f "$MERCHANT_HOME/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$MERCHANT_HOME/.env"
  set +a
fi

ADAPTER_BASE_URL="${ADAPTER_BASE_URL:-http://127.0.0.1:8200}"
MERCHANT_MGMT_API="${MERCHANT_MGMT_API:-http://127.0.0.1:9100}"
HEG_FLIGHT_BACKEND_URL="${HEG_FLIGHT_BACKEND_URL:-http://127.0.0.1:9000}"
HEG_FLIGHT_MCP_SERVER="${HEG_FLIGHT_MCP_SERVER:-$MERCHANT_HOME/../heg_flight_mock/mcp/server.py}"
AP2_ROOT="${AP2_ROOT:-$MERCHANT_HOME/../AP2}"

mkdir -p "$QCLAW_SKILL/scripts" "$QCLAW_SKILL/references"

echo "==> Copy heg-flight skill files"
cp "$SRC_SKILL/SKILL.md" "$QCLAW_SKILL/SKILL.md"
cp "$SRC_SKILL/references/"*.md "$QCLAW_SKILL/references/" 2>/dev/null || true
cp "$SRC_SKILL/scripts/"*.sh "$QCLAW_SKILL/scripts/"
chmod +x "$QCLAW_SKILL/scripts/"*.sh

echo "==> Generate mcporter.json"
python3 - "$QCLAW_SKILL/mcporter.json" \
  "$ADAPTER_MCP" "$TEMP_DB_DIR" "$ADAPTER_BASE_URL" "$MERCHANT_MGMT_API" \
  "$HEG_FLIGHT_BACKEND_URL" "$HEG_FLIGHT_MCP_SERVER" "$AP2_ROOT" <<'PY'
import json, os, sys

(
    out,
    adapter_mcp,
    temp_db,
    adapter_base,
    mm_api,
    heg_url,
    heg_mcp,
    ap2_root,
) = sys.argv[1:9]

cfg = {
    "$schema": "https://raw.githubusercontent.com/steipete/mcporter/main/mcporter.schema.json",
    "mcpServers": {
        "ap2-merchant-adapter": {
            "description": "Agentic Payment Merchant Adapter (UCP + AP2 flight catalog)",
            "command": "python3",
            "args": [adapter_mcp],
            "env": {
                "ADAPTER_BASE_URL": adapter_base,
                "MERCHANT_MGMT_API": mm_api,
                "HEG_FLIGHT_BACKEND_URL": heg_url,
                "HEG_FLIGHT_MCP_SERVER": os.path.expanduser(heg_mcp),
                "TEMP_DB_DIR": temp_db,
                "AP2_ROOT": ap2_root,
            },
        },
        "ap2-buyer": {
            "description": "AP2 buyer: session, mandates, trusted-surface, monitor",
            "baseUrl": "http://127.0.0.1:8100/mcp",
        },
        "ap2-cp": {
            "description": "AP2 mock credentials provider (card + x402)",
            "baseUrl": "http://127.0.0.1:8102/mcp",
        },
        "ap2-mpp": {
            "description": "AP2 mock merchant payment processor",
            "baseUrl": "http://127.0.0.1:8103/mcp",
        },
    },
    "imports": [],
}

with open(out, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY

MCPORTER_PATH="$QCLAW_SKILL/mcporter.json"

if [ -f "$QCLAW_CONFIG" ]; then
  echo "==> Update heg-flight in $QCLAW_CONFIG"
  python3 - "$QCLAW_CONFIG" "$MCPORTER_PATH" "$MERCHANT_HOME" <<'PY'
import json, sys
path, mcporter, merchant_home = sys.argv[1:4]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
entries = cfg.setdefault("skills", {}).setdefault("entries", {})
skill = entries.setdefault("heg-flight", {})
skill["enabled"] = True
skill.setdefault("env", {})["MERCHANT_HOME"] = merchant_home
skill["env"]["MCPORTER_CONFIG"] = mcporter
mcporter_entry = entries.setdefault("mcporter", {})
mcporter_entry["enabled"] = True
for agent in cfg.get("agents", {}).get("list", []):
    names = agent.setdefault("skills", [])
    if "heg-flight" not in names:
        names.append("heg-flight")
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
else
  echo "WARN: $QCLAW_CONFIG not found — enable heg-flight manually" >&2
fi

echo ""
echo "Done. Next steps:"
echo "  1. Restart QClaw"
echo "  2. Start backends:"
echo "       cd $MERCHANT_HOME/../heg_flight_mock && ./scripts/start-backend.sh"
echo "       cd $MERCHANT_HOME && ./scripts/start-all.sh"
echo "       $QCLAW_SKILL/scripts/start-backend.sh"
echo "  3. Onboard HEG → http://127.0.0.1:5273"
echo "  4. Start a NEW chat and try: Book SIN to PVG economy June 21 2026 for 1 adult"
echo ""
echo "Skill path:       $QCLAW_SKILL/SKILL.md"
echo "MCPORTER_CONFIG:  $MCPORTER_PATH"
echo "MERCHANT_HOME:    $MERCHANT_HOME"
