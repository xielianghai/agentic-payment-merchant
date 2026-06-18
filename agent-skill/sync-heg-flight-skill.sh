#!/usr/bin/env bash
# Sync heg-flight from qclaw/heg-flight → openclaw, clawhub/heg-flight, and QClaw install dir.
# Copies shared scripts, patches channel-specific SKILL.md, regenerates mcporter.json.
set -eu

AGENT_SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERCHANT_HOME="$(cd "$AGENT_SKILL_DIR/.." && pwd)"
SRC_SKILL="$AGENT_SKILL_DIR/qclaw/heg-flight"
OPENCLAW_DIR="$AGENT_SKILL_DIR/openclaw"
CLAWHUB_DIR="$AGENT_SKILL_DIR/clawhub/heg-flight"
GENERATE_MCPORTER="$AGENT_SKILL_DIR/scripts/generate-mcporter.py"

QCLAW_SKILL="${QCLAW_SKILL_DIR:-$HOME/.qclaw/skills/heg-flight}"
QCLAW_CONFIG="${QCLAW_CONFIG:-$HOME/.qclaw/openclaw.json}"

SYNC_REPO=1
SYNC_QCLAW=1

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Sync heg-flight skill from agent-skill/qclaw/heg-flight/ to all targets.

  --no-qclaw     Skip ~/.qclaw/skills/heg-flight install
  --qclaw-only   Only install/refresh QClaw (skip openclaw + clawhub)
  -h, --help     Show this help

Default: sync openclaw + clawhub + QClaw install.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-qclaw)
      SYNC_QCLAW=0
      ;;
    --qclaw-only)
      SYNC_REPO=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [ ! -f "$SRC_SKILL/SKILL.md" ]; then
  echo "ERROR: missing $SRC_SKILL/SKILL.md" >&2
  exit 1
fi
if [ ! -f "$GENERATE_MCPORTER" ]; then
  echo "ERROR: missing $GENERATE_MCPORTER" >&2
  exit 1
fi

sync_repo_targets() {
  mkdir -p "$OPENCLAW_DIR/scripts" "$OPENCLAW_DIR/references"
  mkdir -p "$CLAWHUB_DIR/scripts" "$CLAWHUB_DIR/references"

  echo "==> Sync scripts from qclaw/heg-flight"
  cp "$SRC_SKILL/scripts/"*.sh "$OPENCLAW_DIR/scripts/"
  cp "$SRC_SKILL/scripts/"*.sh "$CLAWHUB_DIR/scripts/"
  chmod +x "$OPENCLAW_DIR/scripts/"*.sh "$CLAWHUB_DIR/scripts/"*.sh

  echo "==> Patch SKILL.md for OpenClaw and ClawHub"
  python3 - "$SRC_SKILL/SKILL.md" "$OPENCLAW_DIR/SKILL.md" "$CLAWHUB_DIR/SKILL.md" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="utf-8")

QCLAW_MCPORTER = """6. **mcporter** points at this skill's `mcporter.json` (set automatically by `sync-heg-flight-skill.sh`).

7. Enable **`mcporter`** and **`heg-flight`** in `~/.qclaw/openclaw.json`, then restart QClaw.

Verify: `MERCHANT_HOME=$MERCHANT_HOME ~/.qclaw/skills/heg-flight/scripts/check-backend.sh`"""

DIST_MCPORTER = """6. **mcporter** points at this skill's `mcporter.json` (`MCPORTER_CONFIG=<skill>/mcporter.json`).

7. Enable **`mcporter`** and **`heg-flight`** in your OpenClaw config, then restart the gateway.

Verify: `MERCHANT_HOME=$MERCHANT_HOME <skill>/scripts/check-backend.sh`"""


def patch(content: str, *, title: str) -> str:
    out = content.replace(
        "# HEG Flight Checkout (QClaw + UCP+AP2)",
        title,
    )
    out = out.replace(
        '"$MERCHANT_HOME/agent-skill/qclaw/heg-flight/scripts/start-backend.sh"',
        'MERCHANT_HOME="$MERCHANT_HOME" ./scripts/start-backend.sh',
    )
    out = out.replace(QCLAW_MCPORTER, DIST_MCPORTER)
    out = out.replace(
        '"$MERCHANT_HOME/agent-skill/qclaw/heg-flight/scripts/stop-backend.sh"',
        'MERCHANT_HOME="$MERCHANT_HOME" <skill>/scripts/stop-backend.sh',
    )
    out = out.replace(
        "`~/.qclaw/openclaw.json`",
        "your OpenClaw config",
    )
    out = out.replace(
        "`~/.qclaw/skills/heg-flight/scripts/check-backend.sh`",
        "`<skill>/scripts/check-backend.sh`",
    )
    return out


openclaw = patch(src, title="# HEG Flight Checkout (OpenClaw + UCP+AP2)")
clawhub = patch(src, title="# HEG Flight Checkout (OpenClaw/ClawHub + UCP+AP2)")

Path(sys.argv[2]).write_text(openclaw, encoding="utf-8")
Path(sys.argv[3]).write_text(clawhub, encoding="utf-8")
PY

  echo "==> Generate mcporter.json (relative paths)"
  python3 "$GENERATE_MCPORTER" --mode relative --output "$OPENCLAW_DIR/mcporter.json"
  python3 "$GENERATE_MCPORTER" --mode relative --output "$CLAWHUB_DIR/mcporter.json"
}

install_qclaw_skill() {
  ADAPTER_MCP="$MERCHANT_HOME/adapter/mcp/server.py"
  TEMP_DB_DIR="${TEMP_DB_DIR:-$MERCHANT_HOME/payment-stack/.temp-db}"

  if [ ! -f "$ADAPTER_MCP" ]; then
    echo "ERROR: missing adapter MCP at $ADAPTER_MCP" >&2
    exit 1
  fi

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

  echo "==> Install heg-flight into QClaw ($QCLAW_SKILL)"
  cp "$SRC_SKILL/SKILL.md" "$QCLAW_SKILL/SKILL.md"
  cp "$SRC_SKILL/references/"*.md "$QCLAW_SKILL/references/" 2>/dev/null || true
  cp "$SRC_SKILL/scripts/"*.sh "$QCLAW_SKILL/scripts/"
  chmod +x "$QCLAW_SKILL/scripts/"*.sh

  echo "==> Generate mcporter.json (absolute paths for QClaw)"
  python3 "$GENERATE_MCPORTER" \
    --mode absolute \
    --output "$QCLAW_SKILL/mcporter.json" \
    --merchant-home "$MERCHANT_HOME" \
    --adapter-base-url "$ADAPTER_BASE_URL" \
    --merchant-mgmt-api "$MERCHANT_MGMT_API" \
    --heg-flight-backend-url "$HEG_FLIGHT_BACKEND_URL" \
    --heg-flight-mcp-server "$HEG_FLIGHT_MCP_SERVER" \
    --ap2-root "$AP2_ROOT" \
    --temp-db-dir "$TEMP_DB_DIR"

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
}

if [ "$SYNC_REPO" -eq 1 ]; then
  sync_repo_targets
fi

if [ "$SYNC_QCLAW" -eq 1 ]; then
  install_qclaw_skill
fi

echo ""
echo "Done."
if [ "$SYNC_REPO" -eq 1 ]; then
  echo "  Repo:   $OPENCLAW_DIR"
  echo "          $CLAWHUB_DIR"
fi
if [ "$SYNC_QCLAW" -eq 1 ]; then
  echo "  QClaw:  $QCLAW_SKILL"
  echo "          MCPORTER_CONFIG=$QCLAW_SKILL/mcporter.json"
fi
if [ "$SYNC_REPO" -eq 1 ]; then
  echo ""
  echo "Not modified (channel-specific):"
  echo "  openclaw/README.md"
  echo "  clawhub/heg-flight/PUBLISH.md"
  echo "  references/setup.md under each target"
fi
if [ "$SYNC_QCLAW" -eq 1 ]; then
  echo ""
  echo "Next: restart QClaw, then start backends if needed."
fi
