#!/bin/bash
# ---------------------------------------------------------------------------
# Stop AP2 Unified demo (background or foreground).
#
# Usage: ./stop.sh
# ---------------------------------------------------------------------------

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/demo_lib.sh"
demo_stop_all
