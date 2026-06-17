#!/bin/bash
# Print mock OTP for an openclaw session (AP2_REQUIRE_OTP=1 backend).
# Usage: ./scripts/show_otp.sh <session_id>
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_lib_init

SESSION_ID="${1:-}"
if [ -z "$SESSION_ID" ]; then
  echo "Usage: $0 <session_id>" >&2
  echo "Example: $0 feishu-main" >&2
  exit 1
fi

SAFE="$(printf '%s' "$SESSION_ID" | sed 's/[^a-zA-Z0-9._-]/_/g' | cut -c1-200)"
OTP_FILE="$TEMP_DB/otp_${SAFE}.json"

if [ ! -f "$OTP_FILE" ]; then
  echo "No OTP delivery file: $OTP_FILE" >&2
  echo "Call register_trusted_surface_approval first (returns otp_required)." >&2
  exit 1
fi

python3 - "$OTP_FILE" <<'PY'
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
code = data.get("code", "")
expires = float(data.get("expires_at", 0))
remaining = max(0, int(expires - time.time()))
print(f"session_id: {data.get('session_id', '')}")
print(f"approval_key: {data.get('approval_key', '')}")
print(f"code: {code}")
print(f"expires_in_seconds: {remaining}")
print(f"delivery_path: {path}")
PY
