# Publish ap2-checkout to ClawHub

Maintainer notes (not uploaded as skill body).

## Prerequisites

- `npm i -g clawhub`
- `clawhub login` / `clawhub whoami`
- **`../publish.env`** with your GitHub PAT (see below)
- This folder contains only `SKILL.md` + text assets (ClawHub 50MB text bundle limit).

## GitHub token (config file)

```bash
cd code/samples/python/scenarios/a2a/unified/clawhub
cp publish.env.example publish.env
# Edit publish.env — set GITHUB_TOKEN=ghp_...
```

`publish.env` is gitignored. `publish.sh` loads it automatically.

## Publish

From repository:

```bash
cd code/samples/python/scenarios/a2a/unified/clawhub
chmod +x publish.sh ap2-checkout/scripts/*.sh
# Bump CLAWHUB_VERSION in publish.env and SKILL.md frontmatter, then:
./publish.sh
```

Or manually:

```bash
cd code/samples/python/scenarios/a2a/unified/clawhub/ap2-checkout
chmod +x scripts/check-backend.sh
source ../publish.env

clawhub skill publish . \
  --owner xielianghai \
  --slug ap2-checkout \
  --name "AP2 Checkout (mock)" \
  --version 1.0.3 \
  --changelog "Flight booking: HEG prerequisite, merchant=flight HNP/HP flows, fare monitor wording, verify_checkout_receipt on HP" \
  --clawscan-note "Skill documents localhost-only mock MCP (127.0.0.1:8100-8103) and HTTP triggers 8091-8094; users must clone AP2 and run start_ap2_backend.sh. No external payment APIs."
```

## User install

**Recommended (skill + openclaw + backend):**

```bash
cd "$AP2_HOME"
npx -y file:code/samples/python/scenarios/a2a/unified/clawhub/npm/ap2-agent-checkout install
```

**ClawHub only:**

```bash
clawhub install ap2-checkout
export AP2_HOME=/path/to/AP2
./code/samples/python/scenarios/a2a/unified/openclaw/start_ap2_backend.sh
export MCPORTER_CONFIG=~/.openclaw/workspace/skills/ap2-checkout/mcporter.json
# enable mcporter + ap2-checkout in openclaw.json, restart gateway
```

Public page: `https://clawhub.ai/xielianghai/ap2-checkout`
