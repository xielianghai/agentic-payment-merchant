# AP2 openclaw integration

Run the unified AP2 demo **without** the ADK shopping agent or web UI. openclaw drives the flow via **mcporter** + the **ap2-checkout** skill.

Operation IDs: [../references/demo-ops.md](../references/demo-ops.md).

**ClawHub bundle:** [`../clawhub/ap2-checkout/`](../clawhub/ap2-checkout/).

## Quick start

1. Stop web demo if active: **`ap2.unified.web.stop`**
2. **`ap2.unified.openclaw`**
3. For **flight booking**, also run **`ap2.prereq.heg`** (HEG API on `:9000`) — the openclaw backend does not start HEG.
4. Point `MCPORTER_CONFIG` at this scenario’s `openclaw/mcporter.json`
5. Enable `mcporter` and `ap2-checkout` in `~/.openclaw/openclaw.json` (skill symlink under `~/.openclaw/plugin-skills/ap2-checkout`)
6. Restart openclaw gateway if it was already running

Stop: **`ap2.unified.openclaw.stop`**

## Ports

| Port | Service |
|------|---------|
| 8091 | Merchant trigger (price-drop) |
| 8092 | CP trigger |
| 8093 | MPP card trigger |
| 8094 | x402 PSP trigger |
| 8100 | Buyer MCP (HTTP) |
| 8101 | Merchant MCP (HTTP) |
| 8102 | Credentials provider MCP (HTTP) |
| 8103 | MPP MCP |
| 8104 | H5 Trusted Surface (standalone role) |
| 8105 | HNP monitor scheduler (backend ticks + purchase) |

Do not run **`ap2.unified.openclaw`** alongside **`ap2.unified.web`** — both use 8091–8094 and 8104–8105.

## Feishu / Trusted Surface (H5 portal)

See skill `SKILL.md` and workspace `AGENTS.md`. Default: **H5 Trusted Surface** on port **8104** (`create_trusted_surface_session` → user opens `portal_url` → poll `get_trusted_surface_status`). Legacy OTP when `AP2_REQUIRE_OTP=1`.

Details: [roles/trusted_surface_unified/README.md](../roles/trusted_surface_unified/README.md).

## HNP price monitoring

After `register_price_monitor_tool`, the **monitor scheduler** on port **8105** drives ticks and completes purchase automatically. Do not use `monitor_cron.sh`.

Details: [roles/monitor_scheduler_unified/README.md](../roles/monitor_scheduler_unified/README.md).

## Bot verification (before Feishu / WeChat testing)

1. **`ap2.unified.openclaw.stop`** then **`ap2.unified.openclaw`**
2. Flights: **`ap2.prereq.heg`**
3. **`export MCPORTER_CONFIG=.../openclaw/mcporter.json`**
4. **`./scripts/smoke_openclaw_mcp.sh`**
5. Optional: **`uv run python scripts/smoke_hnp_monitor_scheduler.py`** and **`scripts/e2e_flight_hnp.py`**

Full checklist and bot prompts: **[openclaw/SKILL.md § Bot verification playbook](SKILL.md#bot-verification-playbook-operator--feishuwechat)**.
