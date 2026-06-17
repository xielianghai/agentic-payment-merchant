# AP2 Checkout — setup reference

## Ports (localhost mock)

| Port | Service |
|------|---------|
| 8091 | Merchant trigger (`/trigger-price-drop`) |
| 8092 | Credentials provider trigger |
| 8093 | MPP card trigger |
| 8094 | x402 PSP trigger |
| 8100 | Buyer MCP (HTTP `/mcp`) |
| 8101 | Merchant MCP |
| 8102 | Credentials provider MCP |
| 8103 | MPP MCP |
| 8104 | H5 Trusted Surface |

## AP2_HOME

Must point at the **git clone root** of the AP2 sample repository (not the `unified` subfolder alone).

Example:

```bash
export AP2_HOME="$HOME/Workspaces/ai/AP2"
```

Backend scripts live at:

`$AP2_HOME/code/samples/python/scenarios/a2a/unified/openclaw/start_ap2_backend.sh`

Requires `uv` and Python deps (`uv sync` from `code/samples/python`).

## HEG flight backend (Singapore Airlines mock)

Flight booking (`merchant=flight`) requires HEG separately — **`start_ap2_backend.sh` does not start it**.

From the unified scenario root:

```bash
./demo-op ap2.prereq.heg
```

Default API: `http://127.0.0.1:9000`. If `search_inventory` fails for flights, check HEG first.

## MCPORTER_CONFIG

After `clawhub install`, set:

```bash
export MCPORTER_CONFIG="$HOME/.openclaw/workspace/skills/ap2-checkout/mcporter.json"
```

Adjust path if your OpenClaw workdir differs (`clawhub list` shows install location).

## Smoke test

From a machine with backend running:

```bash
export MCPORTER_CONFIG=".../ap2-checkout/mcporter.json"
cd "$AP2_HOME/code/samples/python/scenarios/a2a/unified"
./scripts/smoke_openclaw_mcp.sh
```

## Logs

`$AP2_HOME/code/samples/python/scenarios/a2a/unified/.logs/`
