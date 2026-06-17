#!/bin/bash
# DEPRECATED: HNP price monitors are driven by monitor_scheduler_unified (:8105).
# OpenClaw cron ticks are no longer required after register_price_monitor_tool.
#
# Legacy driver for AP2 price monitor via OpenClaw cron (/loop is not a substitute).
#
# Usage:
#   ./scripts/monitor_cron.sh start <open_id> [interval_minutes]   # default 5
#   ./scripts/monitor_cron.sh stop  <open_id>
#   ./scripts/monitor_cron.sh delete <open_id>  # immediate removal after purchase
#   ./scripts/monitor_cron.sh status <open_id>
#
# Cron is named  ap2-monitor-<open_id>  and routed to the user's chat channel.
# Each run sends the agent a tight tick instruction. Terminal ticks are one-shot:
# first disable this cron so no more runs fire, then remove it after a grace
# period so QClaw can write the final run to JSONL-backed history.
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-}"
OPEN_ID="${2:-}"
INTERVAL="${3:-5}"

if [ -z "$ACTION" ] || [ -z "$OPEN_ID" ]; then
  echo "Usage: $0 start|stop|delete|status <open_id> [interval_minutes]" >&2
  exit 1
fi

JOB_NAME="ap2-monitor-${OPEN_ID}"
CHANNEL="${AP2_MONITOR_CHANNEL:-${AP2_FEISHU_CHANNEL:-openclaw-weixin}}"
SESSION_KEY="${AP2_MONITOR_SESSION_KEY:-agent:main:${CHANNEL}:direct:${OPEN_ID}}"
TO="${AP2_MONITOR_TO:-user:${OPEN_ID}}"
CLEANUP_DELAY_SECONDS="${AP2_MONITOR_CLEANUP_DELAY_SECONDS:-120}"

OPENCLAW_CMD=()
_configure_openclaw_cmd() {
  if [ -n "${OPENCLAW_BIN:-}" ]; then
    OPENCLAW_CMD=("$OPENCLAW_BIN")
    return 0
  fi
  if command -v openclaw >/dev/null 2>&1; then
    OPENCLAW_CMD=(openclaw)
    return 0
  fi
  local qclaw_json="${QCLAW_JSON:-$HOME/.qclaw/qclaw.json}"
  if [ -f "$qclaw_json" ]; then
    local qclaw_cli
    qclaw_cli="$(python3 - "$qclaw_json" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    cli = data.get("cli") or {}
    node = cli.get("nodeBinary") or ""
    mjs = cli.get("openclawMjs") or ""
    state_dir = data.get("stateDir") or ""
    config = data.get("configPath") or ""
    if node and mjs:
        print(json.dumps({
            "node": node,
            "mjs": mjs,
            "state_dir": state_dir,
            "config": config,
        }))
except Exception:
    pass
PY
)"
    if [ -n "$qclaw_cli" ]; then
      eval "$(python3 - "$qclaw_cli" <<'PY'
import json, shlex, sys
data = json.loads(sys.argv[1])
if data.get("state_dir"):
    print("export OPENCLAW_STATE_DIR=" + shlex.quote(data["state_dir"]))
if data.get("config"):
    print("export OPENCLAW_CONFIG_PATH=" + shlex.quote(data["config"]))
print("OPENCLAW_CMD=(" + " ".join(
    shlex.quote(x) for x in [data["node"], data["mjs"]]
) + ")")
PY
)"
      return 0
    fi
  fi
  echo "ERROR: openclaw CLI not found (set OPENCLAW_BIN or install/open QClaw)." >&2
  exit 1
}

_configure_openclaw_cmd

_job_ids_by_name() {
  "${OPENCLAW_CMD[@]}" cron list --json 2>/dev/null | python3 -c "
import json,sys
name=sys.argv[1]
text=sys.stdin.read()
start=text.find('{')
if start < 0:
    sys.exit(0)
try:
    data=json.loads(text[start:])
except Exception:
    sys.exit(0)
for j in data.get('jobs',[]):
    if j.get('name')==name:
        print(j.get('id',''))
" "$JOB_NAME"
}

_remove_jobs_by_name() {
  ids="$(_job_ids_by_name)"
  if [ -z "$ids" ]; then
    return 1
  fi
  count=0
  while IFS= read -r id; do
    [ -z "$id" ] && continue
    "${OPENCLAW_CMD[@]}" cron rm "$id" >/dev/null 2>&1 || true
    count=$((count + 1))
  done <<EOF
$ids
EOF
  echo "$count"
  return 0
}

_schedule_remove_job_ids() {
  delay="$1"
  ids="$2"
  if [ -z "$ids" ]; then
    return 1
  fi
  (
    sleep "$delay"
    while IFS= read -r id; do
      [ -z "$id" ] && continue
      "${OPENCLAW_CMD[@]}" cron rm "$id" >/dev/null 2>&1 || true
    done <<EOF
$ids
EOF
  ) >/dev/null 2>&1 &
  cleanup_pid=$!
  disown "$cleanup_pid" 2>/dev/null || true
  echo "$delay"
  return 0
}

case "$ACTION" in
  start)
    # Remove all existing jobs with this name first (idempotent re-arm).
    removed="$(_remove_jobs_by_name || true)"
    if [ -n "$removed" ]; then
      echo "Removed ${removed} existing cron job(s) named '$JOB_NAME'."
    fi
    MSG="AP2 price-monitor tick for session ${OPEN_ID}. English only. \
This cron is running in channel '${CHANNEL}' to '${TO}'. Send every user-visible \
monitoring or purchase-complete notification back to this same channel/to. Do not \
write the final purchase result only as a task summary, artifact, or internal note. \
Run EXACTLY this shell command once: ${SCRIPT_DIR}/scripts/monitor_price_tick.sh ${OPEN_ID} \
Then act on its exit code and output: \
- Exit 2 (not due): reply with nothing. \
- Exit 0 (tick recorded): read the LAST JSON object in stdout and post its \
'user_message' (or legacy 'feishu_user_message') to the user verbatim in this \
same channel/to (refs only — never paste shell commands, \
scripts, mcporter, curl, or file paths). Do not rewrite the money fields; \
both Price and Cap must include currency units such as USD. \
- Exit 3 (stop): start your task summary with 'Exit code 3 — constraints met.' \
when stop_reason is constraints_met, or 'Exit code 3 — monitor stopped.' otherwise. \
The tick script has already disabled this schedule and queued delayed cleanup \
after run history is written. Post the LAST JSON's 'user_message' (or legacy \
'feishu_user_message') to this same channel/to. If the \
stop reason is constraints met, continue the HNP purchase flow exactly once WITHOUT \
asking the user for another confirmation. The HNP mandate was already approved and \
signed before monitoring started; do not show a purchase summary that waits for yes, \
approve, or confirm. Do not call set_ap2_session_config, register_trusted_surface_approval, \
verify_payment_otp, or assemble_and_sign_mandates again unless the stored mandate is \
missing or invalid. Use the existing open mandates to assemble_cart, create_checkout, \
create payment/checkout presentations, issue the HNP payment credential, complete_checkout, \
verify the receipt, then call clear_price_monitor_tool. If item not found, tell the user \
monitoring stopped because the item is no longer available. After a successful purchase, \
post a concise purchase success message with product, total, order id, payment method, \
and receipt status to this same channel/to, then emit purchase_complete JSON and stop. \
The scheduled task must be deleted and never run again. Never edit merchant databases or \
backend state to force a price change."
    "${OPENCLAW_CMD[@]}" cron add \
      --name "$JOB_NAME" \
      --every "${INTERVAL}m" \
      --session-key "$SESSION_KEY" \
      --channel "$CHANNEL" \
      --to "$TO" \
      --announce \
      --description "AP2 HNP price monitor for ${OPEN_ID}" \
      --message "$MSG"
    echo "Started cron '$JOB_NAME' every ${INTERVAL}m → ${CHANNEL} ${TO}."
    ;;
  stop)
    ids="$(_job_ids_by_name)"
    if [ -z "$ids" ]; then
      echo "No cron named '$JOB_NAME'."
      exit 0
    fi
    disabled=0
    while IFS= read -r id; do
      [ -z "$id" ] && continue
      "${OPENCLAW_CMD[@]}" cron disable "$id" >/dev/null 2>&1 || true
      disabled=$((disabled + 1))
    done <<EOF
$ids
EOF
    if [ "$CLEANUP_DELAY_SECONDS" = "0" ]; then
      removed="$(_remove_jobs_by_name || true)"
      echo "Stopped ${disabled} cron job(s) named '$JOB_NAME' (disabled now; removed ${removed:-0} immediately)."
      exit 0
    fi
    cleanup_delay="$(_schedule_remove_job_ids "$CLEANUP_DELAY_SECONDS" "$ids" || true)"
    if [ -n "$cleanup_delay" ]; then
      echo "Stopped ${disabled} cron job(s) named '$JOB_NAME' (disabled now; rm queued in ${cleanup_delay}s)."
    else
      echo "Stopped ${disabled} cron job(s) named '$JOB_NAME' (disabled now; no rm cleanup queued)."
    fi
    ;;
  delete)
    removed="$(_remove_jobs_by_name || true)"
    if [ -n "$removed" ]; then
      echo "Deleted ${removed} cron job(s) named '$JOB_NAME'."
    else
      echo "No cron named '$JOB_NAME'."
    fi
    ;;
  status)
    ids="$(_job_ids_by_name)"
    if [ -z "$ids" ]; then
      echo "No cron named '$JOB_NAME'."
    else
      while IFS= read -r id; do
        [ -z "$id" ] && continue
        "${OPENCLAW_CMD[@]}" cron show "$id" 2>/dev/null || echo "Job id: $id"
      done <<EOF
$ids
EOF
    fi
    ;;
  *)
    echo "Unknown action: $ACTION (use start|stop|delete|status)" >&2
    exit 1
    ;;
esac
