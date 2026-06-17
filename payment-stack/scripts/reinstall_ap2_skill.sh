#!/bin/bash
# Reinstall ap2-checkout skill into QClaw skills dir and refresh English SKILL text.
set -eu

UNIFIED="$(cd "$(dirname "$0")/.." && pwd)"
AP2_HOME="${AP2_HOME:-$(cd "$UNIFIED/../../../../../.." && pwd)}"

# QClaw: local import / chat install target (~/.qclaw/skills).
# Override with AP2_SKILL_DIR for a custom path.
QCLAW_SKILL="${AP2_SKILL_DIR:-$HOME/.qclaw/skills/ap2-checkout}"
QCLAW_CONFIG="${QCLAW_CONFIG:-$HOME/.qclaw/openclaw.json}"
QCLAW_WORKSPACE="${QCLAW_WORKSPACE:-$HOME/.qclaw/workspace}"
SRC_SKILL="$UNIFIED/openclaw/SKILL.md"
CLAWHUB_SKILL="$UNIFIED/clawhub/ap2-checkout"

if [ ! -f "$SRC_SKILL" ]; then
  echo "ERROR: missing $SRC_SKILL" >&2
  exit 1
fi

mkdir -p "$QCLAW_SKILL/scripts" "$QCLAW_SKILL/references"

# IMPORTANT: copy the LOCAL repo SKILL last so local edits always win.
# (Running `clawhub install --force` here would overwrite the skill with the
#  published version and silently revert local changes.)
echo "==> Copy SKILL.md from repo (English + OTP refs + monitor; local wins)"
cp "$SRC_SKILL" "$QCLAW_SKILL/SKILL.md"
cp "$CLAWHUB_SKILL/mcporter.json" "$QCLAW_SKILL/mcporter.json"
cp "$CLAWHUB_SKILL/scripts/"*.sh "$QCLAW_SKILL/scripts/" 2>/dev/null || true
cp "$CLAWHUB_SKILL/references/"*.md "$QCLAW_SKILL/references/" 2>/dev/null || true
# Drop stale QClaw-only scripts (monitor uses repo unified/scripts/monitor_cron.sh).
for stale in monitor_cron.sh hnp_purchase_once.sh; do
  if [ -f "$QCLAW_SKILL/scripts/$stale" ] && [ ! -f "$CLAWHUB_SKILL/scripts/$stale" ]; then
    rm -f "$QCLAW_SKILL/scripts/$stale"
    echo "    Removed stale script: scripts/$stale"
  fi
done
echo "    NOTE: do NOT run 'clawhub install ap2-checkout --force' after this —"
echo "          the published version is older and will revert these local edits."

MCPORTER_PATH="$QCLAW_SKILL/mcporter.json"
if [ -f "$QCLAW_CONFIG" ]; then
  echo "==> Update ap2-checkout env in $QCLAW_CONFIG"
  python3 - "$QCLAW_CONFIG" "$MCPORTER_PATH" "$AP2_HOME" <<'PY'
import json, sys
path, mcporter, ap2_home = sys.argv[1:4]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
entries = cfg.setdefault("skills", {}).setdefault("entries", {})
ap2 = entries.setdefault("ap2-checkout", {})
ap2["enabled"] = True
ap2.setdefault("env", {})["AP2_HOME"] = ap2_home
ap2["env"]["MCPORTER_CONFIG"] = mcporter
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
fi

echo "==> Sync AGENTS.md / SOUL.md language hints"
for f in AGENTS.md SOUL.md; do
  if [ -f "$QCLAW_WORKSPACE/$f" ]; then
    if ! grep -q "## Language" "$QCLAW_WORKSPACE/$f" 2>/dev/null; then
      echo "    WARN: add Language section to $QCLAW_WORKSPACE/$f manually"
    fi
  fi
done

echo "==> Skill status"
if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW_CONFIG="$QCLAW_CONFIG" openclaw skills list 2>/dev/null | grep -i ap2-checkout || true
else
  echo "    (openclaw CLI not in PATH — skip skills list)"
fi

echo ""
echo "Done. Next steps:"
echo "  1. Restart QClaw (or: openclaw gateway restart with QCLAW_CONFIG=$QCLAW_CONFIG)"
echo "  2. Start a NEW chat thread (old sessions keep stale skill snapshots)"
echo "  3. Try: Launch AP2 payment"
echo ""
echo "Skill path: $QCLAW_SKILL/SKILL.md"
echo "MCPORTER_CONFIG: $MCPORTER_PATH"
echo "AP2_HOME: $AP2_HOME"
