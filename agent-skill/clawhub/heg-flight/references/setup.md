# HEG Flight skill — setup reference

## MERCHANT_HOME

Absolute path to the **agentic-payment-merchant** repository root.

```bash
export MERCHANT_HOME="$HOME/AI-coding/payment/agentic-payment-merchant"
```

## Ports

| Port | Service |
|------|---------|
| 9000 | HEG Flight API |
| 9100 | Merchant Management API |
| 5273 | Merchant Management UI |
| 8200 | Adapter (UCP facade) |
| 8092 | CP trigger |
| 8093 | MPP card trigger |
| 8094 | x402 PSP trigger |
| 8100 | Buyer MCP (`/mcp`) |
| 8102 | Credentials provider MCP |
| 8103 | MPP MCP |
| 8104 | H5 Trusted Surface |
| 8105 | HNP monitor scheduler |

Merchant catalog tools use **Adapter MCP** (`ap2-merchant-adapter`, stdio) — not port 8101.

## OpenClaw local install

From this repository:

```bash
export MERCHANT_HOME=/path/to/agentic-payment-merchant
export OPENCLAW_SKILL_DIR=$HOME/.openclaw/skills/heg-flight
mkdir -p "$OPENCLAW_SKILL_DIR"
cp -R "$MERCHANT_HOME/agent-skill/openclaw/"* "$OPENCLAW_SKILL_DIR/"
export MCPORTER_CONFIG="$OPENCLAW_SKILL_DIR/mcporter.json"
```

The source `agent-skill/openclaw/mcporter.json` uses paths relative to this repository. If you copy the skill elsewhere, regenerate it or update `ap2-merchant-adapter.args` and env paths to absolute paths for your machine.

## QClaw install

```bash
cd "$MERCHANT_HOME/agent-skill"
./sync-heg-flight-skill.sh
```

Target: `~/.qclaw/skills/heg-flight/`

Override paths:

```bash
QCLAW_SKILL_DIR=~/.qclaw/skills/heg-flight QCLAW_CONFIG=~/.qclaw/openclaw.json ./sync-heg-flight-skill.sh
```

## Smoke check

```bash
MERCHANT_HOME=$MERCHANT_HOME ~/.qclaw/skills/heg-flight/scripts/check-backend.sh
```

## Logs

- `$MERCHANT_HOME/.logs/` — MM, Adapter
- `$MERCHANT_HOME/payment-stack/.logs/` — payment stack, buyer MCP
- `$MERCHANT_HOME/payment-stack/.temp-db/` — session / mandate state
