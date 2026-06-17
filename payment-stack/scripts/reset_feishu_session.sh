#!/bin/bash
# Archive the current Feishu DM session so the next message starts fresh (English rules apply).
# Usage: ./scripts/reset_feishu_session.sh [feishu_open_id]
set -eu

FEISHU_USER="${1:-ou_d422679d1e7ad702db1139fad9ad8221}"
SESSION_KEY="agent:main:feishu:direct:${FEISHU_USER}"
STORE="${OPENCLAW_SESSIONS:-$HOME/.openclaw/agents/main/sessions/sessions.json}"
AGENTS_DIR="$(dirname "$STORE")"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_DIR="$AGENTS_DIR/archive-$STAMP"
mkdir -p "$ARCHIVE_DIR"

if [ ! -f "$STORE" ]; then
  echo "ERROR: session store not found: $STORE" >&2
  exit 1
fi

python3 - "$STORE" "$SESSION_KEY" "$ARCHIVE_DIR" <<'PY'
import json
import shutil
import sys
from pathlib import Path

store_path = Path(sys.argv[1])
session_key = sys.argv[2]
archive_dir = Path(sys.argv[3])

data = json.loads(store_path.read_text(encoding="utf-8"))
entry = data.pop(session_key, None)
if not entry:
    print(f"No session row for {session_key!r}")
    sys.exit(0)

store_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
session_id = entry.get("sessionId", "")
session_file = entry.get("sessionFile") or ""
archived = []
if session_file:
    src = Path(session_file)
    if src.is_file():
        dst = archive_dir / src.name
        shutil.move(str(src), str(dst))
        archived.append(str(dst))
        traj = src.parent / f"{src.stem}.trajectory.jsonl"
        if traj.is_file():
            tdst = archive_dir / traj.name
            shutil.move(str(traj), str(tdst))
            archived.append(str(tdst))

(archive_dir / "session-entry.json").write_text(
    json.dumps(entry, indent=2, ensure_ascii=True), encoding="utf-8"
)
print(f"Removed session key: {session_key}")
print(f"Session id: {session_id}")
for p in archived:
    print(f"Archived: {p}")
print(f"Entry backup: {archive_dir / 'session-entry.json'}")
PY

echo ""
echo "Done. Send your next Feishu message — OpenClaw will start a NEW session."
echo "Try: Launch AP2 payment"
echo "Or in chat: /new"
