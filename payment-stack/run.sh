#!/bin/bash
# ---------------------------------------------------------------------------
# AP2 Unified demo (legacy entry — foreground mode).
#
# Prefer:
#   ./start.sh          # background
#   ./stop.sh           # stop
#   ./start.sh --foreground   # same as this script
# ---------------------------------------------------------------------------

set -eu
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start.sh" --foreground "$@"
