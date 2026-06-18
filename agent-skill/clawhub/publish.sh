#!/usr/bin/env bash
# Publish heg-flight skill to ClawHub (maintainer).
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/heg-flight"
ENV_FILE="$SCRIPT_DIR/publish.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if ! command -v clawhub >/dev/null 2>&1; then
  echo "ERROR: clawhub CLI not found" >&2
  exit 1
fi

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  echo "ERROR: missing $SKILL_DIR/SKILL.md" >&2
  exit 1
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: set GITHUB_TOKEN in $ENV_FILE" >&2
  exit 1
fi

chmod +x "$SKILL_DIR/scripts/"*.sh

clawhub publish "$SKILL_DIR" \
  --slug heg-flight \
  --version "${CLAWHUB_VERSION:-1.0.0}" \
  --changelog "${CLAWHUB_CHANGELOG:-HEG Flight checkout via Agentic Payment Merchant Adapter}"

echo "Done. Install: clawhub install heg-flight"
