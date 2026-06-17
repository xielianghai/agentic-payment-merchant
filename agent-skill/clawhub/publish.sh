#!/usr/bin/env bash
# Publish ap2-checkout skill to ClawHub (maintainer).
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/ap2-checkout"
ENV_FILE="$SCRIPT_DIR/publish.env"

# Load token and overrides from publish.env (gitignored).
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
elif [ -f "$SCRIPT_DIR/publish.env.example" ]; then
  echo "Hint: cp $SCRIPT_DIR/publish.env.example $ENV_FILE and set GITHUB_TOKEN" >&2
fi

OWNER="${CLAWHUB_OWNER:-xielianghai}"
VERSION="${CLAWHUB_VERSION:-1.0.3}"

chmod +x "$SKILL_DIR"/scripts/*.sh 2>/dev/null || true

if ! command -v clawhub >/dev/null 2>&1; then
  echo "ERROR: install clawhub — npm i -g clawhub" >&2
  exit 1
fi

if [ -z "${GITHUB_TOKEN:-}${GH_TOKEN:-}" ]; then
  echo "ERROR: set GITHUB_TOKEN in $ENV_FILE (copy from publish.env.example)" >&2
  exit 1
fi

export GITHUB_TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

clawhub whoami

clawhub skill publish "$SKILL_DIR" \
  --owner "$OWNER" \
  --slug ap2-checkout \
  --name "AP2 Checkout (mock)" \
  --version "$VERSION" \
  --changelog "${CLAWHUB_CHANGELOG:-One-command npx installer docs; clawhub install ap2-checkout; AP2_INSTALL_QUICK backend}" \
  --clawscan-note "Localhost mock only: MCP 8100-8103 and triggers 8091-8094 on 127.0.0.1. Users clone AP2 repo, set AP2_HOME, run start_ap2_backend.sh. Simulated card/x402; no real payment network."

echo ""
echo "Done. Install: clawhub install ap2-checkout"
echo "One-shot: npx -y file:\$AP2_HOME/code/samples/python/scenarios/a2a/unified/clawhub/npm/ap2-agent-checkout install"
