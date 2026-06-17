---
name: heg-flight
description: |
  HEG Flight booking via Agentic Payment Merchant (English replies only). Use for
  Singapore Airlines flight search, HP buy-now, and HNP fare-watch checkout through
  UCP+AP2 mock stack. Requires local HEG, Adapter, and payment backend.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "✈️",
        "requires": { "bins": ["mcporter", "curl", "python3"] },
      },
  }
---

# HEG Flight Checkout (QClaw + UCP+AP2)

**Language (mandatory):** Reply in **English** — summaries, fare tables, errors, portal/monitor prompts. The user may write Chinese (e.g. 我要买机票); **still respond in English** unless they explicitly ask for Chinese.

Drive **Singapore Airlines mock flight booking** via **mcporter**:

| Server | Role |
|--------|------|
| `ap2-merchant-adapter` | Flight catalog / cart / checkout (UCP → HEG) |
| `ap2-buyer` | Session config, mandates, Trusted Surface, price monitor |
| `ap2-cp` | `issue_payment_credential` |
| `ap2-mpp` | Settlement (rare in demo) |

All payments are **simulated** — no real card or crypto settlement.

## When to use this skill

Match **flight booking** intents first:

- "book a flight", "buy airline tickets", "Singapore Airlines SIN to PVG", **我要买机票**, **订机票**

Collect route / date / cabin / passengers / budget (HNP) **before** the first tool call.

## Prerequisites

1. **Clone & env** — set `MERCHANT_HOME` to this repository root:

```bash
export MERCHANT_HOME="/path/to/agentic-payment-merchant"
cp "$MERCHANT_HOME/.env.example" "$MERCHANT_HOME/.env"
```

2. **HEG Flight** (external repo, port 9000):

```bash
cd "$MERCHANT_HOME/../heg_flight_mock"
./scripts/start-backend.sh
```

3. **Merchant stack** (MM :9100, Adapter :8200, payment triggers/TS/monitor):

```bash
cd "$MERCHANT_HOME"
./scripts/start-all.sh
```

4. **Buyer MCP HTTP** (ports 8100 / 8102 / 8103) — if not already listening:

```bash
"$MERCHANT_HOME/agent-skill/qclaw/heg-flight/scripts/start-backend.sh"
```

5. **Onboard HEG** in Merchant Management → http://127.0.0.1:5273 → one-click onboard HEG Flight.

6. **mcporter** points at this skill's `mcporter.json` (set automatically by `install-qclaw-skill.sh`).

7. Enable **`mcporter`** and **`heg-flight`** in `~/.qclaw/openclaw.json`, then restart QClaw.

Verify: `MERCHANT_HOME=$MERCHANT_HOME ~/.qclaw/skills/heg-flight/scripts/check-backend.sh`

## Session identity (CRITICAL)

**`session_id` = this chat user's channel peer id** (Feishu `open_id`, WeChat open id, etc.).

- Use the **same** id on every `ap2-buyer.*` call in this chat.
- **NEVER** use placeholders like `CHAT_ID`, `feishu-main`, or invented suffixes.
- **Monitor ref** / **OTP ref** shown to the user is this same id.

```bash
mcporter list ap2-merchant-adapter --schema
mcporter list ap2-buyer --schema
mcporter list ap2-cp --schema
```

## Mode selection (always first)

| User intent | merchant | presence_mode | payment_method |
|-------------|----------|---------------|----------------|
| Book / buy flights now | `flight` | `hp` | `card` (default) or `x402` |
| Watch fare / buy when ≤ budget | `flight` | `hnp` | `card` or `x402` |

```bash
mcporter call ap2-buyer.set_ap2_session_config_tool \
  session_id=<OPEN_ID> presence_mode=hp payment_method=card merchant=flight
mcporter call ap2-buyer.get_ap2_session_config_tool session_id=<OPEN_ID>
```

Read **`merchant_instruction`** from the config result — authoritative for currency (USD) and flight rules.

## Flight booking flow

Singapore Airlines mock (HEG). Currency: **USD**.

### Collect intent (before tools)

| Field | Example | Notes |
|-------|---------|-------|
| Origin / destination | SIN → PVG | IATA codes |
| Date | 2026-06-21 | use explicit future dates |
| Cabin | economy | economy / business |
| Passengers | 1 adult | maps to `qty` |
| Budget | USD 600 | **required for HNP** |
| Payment | card | or x402 if user says crypto |

### Search and present

```bash
mcporter call ap2-merchant-adapter.search_inventory \
  product_description="SIN to PVG economy June 21 2026 1 adult" \
  constraint_price_cap=600
```

Present a **numbered list** using `display_name` / `product_label` — never raw routing keys as the main line. User picks → use that `item_id` for all later steps.

### MCP routing (mandatory)

| Action | Server | Tool |
|--------|--------|------|
| Session, mandates, TS portal | `ap2-buyer` | `create_trusted_surface_session`, `assemble_and_sign_*`, `register_price_monitor_tool` |
| Flight catalog / cart / checkout | **`ap2-merchant-adapter`** | `search_inventory`, `check_product`, `assemble_cart`, `create_checkout`, `complete_checkout` |
| Payment credential | **`ap2-cp`** | **`issue_payment_credential`** |

**`issue_payment_credential` is only on `ap2-cp`.** Wrong server → fix prefix and continue from last good step.

## Feishu / WeChat user messages

Never show shell commands, `mcporter`, `curl`, or file paths in chat.

| Situation | Tell the user |
|-----------|----------------|
| Trusted Surface | **`portal_url`** from `user_message` |
| Price / fare monitor | **Monitor ref:** `session_id` |
| No seats | Suggest another date or route |
| Flight line | `display_name` — not raw routing keys |

Post tool **`user_message`** / **`feishu_user_message`** verbatim in the initiating channel.

## Trusted Surface (H5 portal)

Show an English purchase summary (flight, fare, payment rail). Wait for **yes / approve / confirm**.

**HNP flight** (`price_cap` = user budget USD):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=<OPEN_ID> price_cap=600 payment_method=card presence_mode=hnp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-21 · Economy"
```

**HP flight** (after `create_checkout` — pass **`amount_cents`** from checkout total):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=<OPEN_ID> amount_cents=50630 price_cap=506.30 payment_method=card presence_mode=hp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-21 · Economy"
```

1. Post **`user_message`** verbatim. Remember exact **`ref`**.
2. Long-poll:

```bash
mcporter call ap2-buyer.wait_for_trusted_surface_signed ref=REF_FROM_STEP_1 timeout_seconds=300
```

3. On **`signed`** → `assemble_and_sign_*` on same `session_id`, continue without a new portal.

## HNP flow (fare watch)

1. `set_ap2_session_config` → `merchant=flight`, `hnp`, `card` or `x402`.
2. `ap2-merchant-adapter.search_inventory` → user picks flight.
3. `ap2-merchant-adapter.check_product` with user budget.
4. Mandate summary → confirm → Trusted Surface → `assemble_and_sign_mandates`.
5. Ask monitor interval (default 5 min, minimum 1 min):

```bash
mcporter call ap2-buyer.register_price_monitor_tool \
  session_id=<OPEN_ID> item_id=ITEM_ID price_cap=600 interval_minutes=5 \
  item_name="SQ836 SIN→PVG · 2026-06-21 · Economy" merchant=flight
```

6. Poll `get_price_monitor_status_tool` until `purchased`, `stopped`, or `error`. Backend scheduler on **:8105** completes purchase automatically when fare ≤ budget and seats exist.

**Never** show Drop ref or shoe trigger curl for flights.

## HP flow (buy now)

1. `set_ap2_session_config` → `merchant=flight`, `hp`, `card` or `x402`.
2. `search_inventory` → user picks → `check_product` → `assemble_cart` (`qty` = passengers).
3. `create_hp_open_mandates` (once per purchase).
4. `ap2-merchant-adapter.create_checkout` with `open_checkout_mandate_id`.
5. Checkout summary → user confirm → Trusted Surface with `amount_cents` → `wait_for_trusted_surface_signed`.
6. On signed: `assemble_and_sign_immediate_mandates` → **`ap2-cp.issue_payment_credential`** → **`ap2-merchant-adapter.complete_checkout`** → `verify_checkout_receipt_tool` → post booking confirmed + **`purchase_complete`** JSON.

**Never** call `create_hp_open_mandates` twice. **Never** restart from step 1 after TS is signed — retry the failed step only.

## Errors

If any tool returns `"error"`, stop and report `message`. Check:

- HEG on `:9000`
- Adapter on `:8200`
- Buyer MCP on `:8100`
- Logs under `$MERCHANT_HOME/payment-stack/.logs/` and `$MERCHANT_HOME/.logs/`

## Stop

```bash
cd "$MERCHANT_HOME" && ./scripts/stop-all.sh
"$MERCHANT_HOME/agent-skill/qclaw/heg-flight/scripts/stop-backend.sh"
```
