# HEG Flight OpenClaw Skill

OpenClaw skill bundle for **Singapore Airlines / HEG Flight** checkout through
Agentic Payment Merchant.

This is the OpenClaw counterpart of `agent-skill/qclaw/heg-flight/`. It uses the
same MCP servers and business flow:

- `ap2-merchant-adapter` for flight catalog, cart, checkout, and completion
- `ap2-buyer` for session config, mandates, Trusted Surface, and monitor
- `ap2-cp` for payment credentials
- `ap2-mpp` for settlement

## Local Use

From the repository root:

```bash
export MERCHANT_HOME="$PWD"
export MCPORTER_CONFIG="$PWD/agent-skill/openclaw/mcporter.json"
```

Start prerequisites:

```bash
cd "$MERCHANT_HOME/../heg_flight_mock" && ./scripts/start-backend.sh
cd "$MERCHANT_HOME" && ./scripts/start-all.sh
MERCHANT_HOME="$MERCHANT_HOME" "$MERCHANT_HOME/agent-skill/openclaw/scripts/start-backend.sh"
```

Then enable `mcporter` and `heg-flight` in your OpenClaw config and restart the
gateway.

## Notes

`mcporter.json` in this folder is a repository-local development config. If you
copy this skill to another folder, regenerate `mcporter.json` with absolute
paths or update the relative paths manually.
