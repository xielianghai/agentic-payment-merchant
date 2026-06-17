# Monitor scheduler (HNP backend)

Standalone HTTP service on port **8105** that drives **Human Not Present (HNP)** price monitoring without OpenClaw cron or browser `setInterval` loops.

## Role

After the user signs open mandates, a monitor is armed in shared session storage (`.temp-db/session_<id>.json`). This service:

1. Polls active monitors on a background thread (default every 5s).
2. Calls merchant `check_product` and buyer `check_constraints` when a tick is due.
3. When constraints are met, runs a **deterministic in-process purchase chain** (no LLM).
4. Sends optional OpenClaw wake notifications on ticks, purchase complete, or stop.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status |
| GET | `/monitor/status?session_id=` | Monitor status (+ last tick artifact, `purchase_complete` when done) |
| POST | `/monitor/register` | Arm monitor; web clients pass `session_state` / open mandate ids |

## Start

Started automatically by **`ap2.unified.web`** (`start.sh`) and **`ap2.unified.openclaw`** (`openclaw/start_ap2_backend.sh`).

Manual:

```bash
cd code/samples/python/scenarios/a2a/unified/roles/monitor_scheduler_unified
uv run --package ap2-samples python server.py
```

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `UNIFIED_MONITOR_SCHEDULER_PORT` | `8105` | HTTP port |
| `MONITOR_SCHEDULER_POLL_SECONDS` | `5` | Scheduler loop interval |
| `AP2_OPENCLAW_HOOK_ENABLED` | `1` | Send tick/purchase notifications via OpenClaw hook |
| `TEMP_DB_DIR` | `.temp-db` | Shared session files |

## openclaw flow

1. Agent calls `register_price_monitor_tool` (buyer MCP) after mandate signing.
2. Backend scheduler ticks and purchases automatically.
3. Agent posts the tool's `feishu_user_message`; optional status poll via `get_price_monitor_status_tool`.

Do **not** run `scripts/monitor_cron.sh` or `scripts/monitor_price_tick.sh` (deprecated).

## Web flow

When the chat UI shows a **monitoring** artifact, it calls `POST /monitor/register` with the A2A `session_id` and open mandate ids, then polls `GET /monitor/status` every 5s for UI updates only.

Configure with `VITE_MONITOR_SCHEDULER_URL` (default `http://localhost:8105`).

## Verification

```bash
# Health
curl -s http://localhost:8105/health

# Register (after mandates exist in session file or via session_state)
curl -s -X POST http://localhost:8105/monitor/register \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"test-session","item_id":"slug_0","price_cap":200,"merchant":"shoe"}'

# Status
curl -s 'http://localhost:8105/monitor/status?session_id=test-session'
```

Trigger a shoe price drop (merchant trigger on :8091), then confirm status moves to `purchased` with `purchase_complete`.

Full E2E smoke (demo stack must be running on :8105 and :8091):

```bash
cd code/samples/python/scenarios/a2a/unified
uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py
```

This assembles HNP mandates, `POST /monitor/register`, triggers a price drop, and polls until `status=purchased` (~20s).
