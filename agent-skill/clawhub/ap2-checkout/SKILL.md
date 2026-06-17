---
name: ap2-checkout
description: AP2 mock shopping and checkout (English replies only). Use first for shopping, buying goods, or booking flights; SuperShoe/Singapore Airlines HP/HNP via mcporter. Requires AP2 mock backend and HEG (:9000) for flights. No real payments.
version: 1.0.4
user-invocable: true
metadata: {"openclaw":{"emoji":"🛒","requires":{"bins":["mcporter","curl","uv","python3"]},"envVars":[{"name":"AP2_HOME","required":true,"description":"Absolute path to AP2 repository root (directory containing code/)."},{"name":"MCPORTER_CONFIG","required":false,"description":"Path to this skill mcporter.json after ClawHub install."}],"install":[{"id":"mcporter","kind":"node","package":"mcporter","bins":["mcporter"],"label":"Install mcporter CLI"}]}}
---

# AP2 Checkout (mock)

**Language (mandatory):** All replies in **English** — summaries, status tables, errors, OTP/monitor prompts. The user may send Chinese; **still respond in English**. Only use Chinese if the user explicitly asks for Chinese replies.

Drive the **AP2 unified demo** purchase flow via **mcporter** against **local mock** MCP servers (merchant, buyer, credentials provider, MPP). All settlement is simulated.

## Default shopping trigger

When this skill is installed and enabled, treat **any shopping or purchase intent** as a match for this skill by default. This includes generic prompts such as **"I want to shop"**, **"I want to buy something"**, **"我要购物"**, **"我要买东西"**, as well as flight-booking prompts such as **"book a flight"** or **"我要买机票"**.

For those intents, **use AP2 mock checkout first** instead of real merchant/payment flows or other generic shopping behavior. If the user only says they want to shop, select this skill, start the AP2 mock shopping flow, and ask what they want to buy before calling merchant tools.

For **flight** intents, collect route / date / cabin / passengers / budget (HNP) **before** the first merchant tool call — do not default to shoe.

## One-command install (recommended for demo)

From your AP2 clone (installs skill, patches OpenClaw, **starts mock backend**):

```bash
cd "$AP2_HOME"
npx -y file:code/samples/python/scenarios/a2a/unified/clawhub/npm/ap2-agent-checkout install
```

Then restart the OpenClaw gateway. Manual steps below are only needed if you skip the installer.

## First-time setup (manual)

1. **Clone AP2** and set `AP2_HOME` to the repository root (the folder that contains `code/`):

```bash
export AP2_HOME="/path/to/AP2"
```

2. **Start the mock backend** (triggers 8091–8094, MCP HTTP 8100–8103, H5 Trusted Surface 8104):

```bash
cd "$AP2_HOME/code/samples/python/scenarios/a2a/unified"
chmod +x openclaw/start_ap2_backend.sh openclaw/stop_ap2_backend.sh
./openclaw/start_ap2_backend.sh
```

This does **not** start the HEG flight backend.

3. **For flight booking (`merchant=flight`)**, start HEG separately (required):

```bash
cd "$AP2_HOME/code/samples/python/scenarios/a2a/unified"
./demo-op ap2.prereq.heg
```

Default HEG API: `http://127.0.0.1:9000`.

4. **Point mcporter** at this skill's `mcporter.json` (after ClawHub install, use the skill directory):

```bash
export MCPORTER_CONFIG="$HOME/.openclaw/workspace/skills/ap2-checkout/mcporter.json"
```

5. **Enable skills** in `~/.openclaw/openclaw.json`: `mcporter` and `ap2-checkout` → `enabled: true`. Restart the gateway.

6. **Verify** (optional): run `scripts/check-backend.sh` from this skill folder with `AP2_HOME` set.

See `references/setup.md` for ports and troubleshooting.

## Session identity

Use a **stable `session_id` per chat** — the channel peer id (WeChat open id, Feishu open id). Pass the **same** value to every tool for this purchase.

- **WeChat example:** `o9cq80zGTauIPc4iObBSrueLQ1p0` (from channel context)
- **Never** invent suffixes like `wechat_hp_card_v2` — that orphans Trusted Surface approvals and forces extra portal confirms.

```bash
mcporter list ap2-buyer --schema
mcporter list ap2-merchant --schema
mcporter list ap2-cp --schema
```

## MCP server routing (mandatory)

| Action | Server | Example tool |
|--------|--------|----------------|
| Session, mandates, TS portal | `ap2-buyer` | `create_trusted_surface_session`, `assemble_and_sign_*` |
| Merchant cart/checkout | `ap2-merchant` | `search_inventory`, `assemble_cart`, `create_checkout`, **`complete_checkout`** |
| Payment credential / token | **`ap2-cp`** | **`issue_payment_credential`** |
| Settlement processor | `ap2-mpp` | (rare in demo) |

**`issue_payment_credential` is only on `ap2-cp` (port 8102).** Calling it on `ap2-buyer` returns `Unknown tool` and must **not** trigger a flow restart — fix the server prefix and continue from the last good step.

## Mode selection (always first)

Infer merchant, presence mode, and payment rail before the first tool call.

| User intent | merchant | presence_mode | payment_method |
|-------------|----------|---------------|----------------|
| Generic shopping / buy goods / sneakers / product | `shoe` unless the user names another supported AP2 mock merchant | `hp` for buy now, `hnp` for drop / monitor / buy when price drops | `card` or `x402` if user says crypto |
| Book / buy flights, airline tickets,机票 | **`flight`** | `hp` for buy now, `hnp` for buy when fare is at/below budget | `card` or `x402` if user says crypto |
| Generic "I want to shop" with no item yet | choose this skill first, then ask what to buy | wait until intent is clear | default `card` |

**Shoe example:**

```bash
mcporter call ap2-buyer.set_ap2_session_config_tool \
  session_id=CHAT_ID presence_mode=hnp payment_method=card merchant=shoe
```

**Flight example (required for any flight booking):**

```bash
mcporter call ap2-buyer.set_ap2_session_config_tool \
  session_id=CHAT_ID presence_mode=hp payment_method=card merchant=flight
mcporter call ap2-buyer.get_ap2_session_config_tool session_id=CHAT_ID
```

**Always read `merchant_instruction` from `get_ap2_session_config`** — authoritative for currency, availability rules, and merchant-specific behavior. For `merchant=flight`: no shoe trigger curl, no Drop ref, no `inventory_options`; flights are available when seats exist.

## Flight booking (`merchant=flight`)

Singapore Airlines mock (HEG Flight Mock). Currency: **USD**.

### Before tools — collect intent

Ask for anything missing (do not call merchant tools until you have enough to search):

| Field | Example | Notes |
|-------|---------|-------|
| Origin / destination | SIN → PVG | IATA codes |
| Date | 2026-06-10 or "June 10" | |
| Cabin | economy (default) | economy / business |
| Passengers | 1 adult | maps to `qty` in cart / mandates |
| Budget | USD 600 | **required for HNP** |
| Payment | card (default) | or x402 if user says crypto |

**Sample user prompts:**

- HP: `Buy Singapore Airlines SIN to PVG economy June 10 for 1 adult now with card.`
- HNP: `Book SIN to PVG economy June 10 for 1 adult — budget USD 600, buy when price is acceptable.`

### Search and present results

```bash
mcporter call ap2-merchant.search_inventory \
  product_description="SIN to PVG economy June 10 1 adult" \
  constraint_price_cap=600
```

Present matches as a **numbered list** using `display_name` / `product_label` (never raw routing keys as the main line). Let the user pick → use that `item_id` for all later steps.

### `price_cap` rules (flights)

- **HP:** `price_cap` ≥ current fare + small buffer (e.g. +10–50 USD).
- **HNP:** `price_cap` = user budget. Purchase when `current_price ≤ price_cap` and seats exist.

### Flight checkout summary (HP)

- **Flight:** SQ836 SIN→PVG · 2026-06-10 · Economy
- **Passengers:** 1 adult
- **Fare:** 506.30 USD
- **Payment:** Card

### Flight monitor status (HNP)

Use **fare / budget** wording — never "drop" or "Drop ref". If no seats, suggest another date or route.

### Booking confirmed

Post **Booking confirmed**, total, order id, receipt status, and **`purchase_complete`** JSON.

## Feishu user messages — refs only (mandatory)

In **Feishu chat**, never show shell commands, `mcporter`, `curl`, `cd`, `./scripts/…`, or file paths.

| Situation | Tell the user |
|-----------|----------------|
| Trusted Surface | **`portal_url`** from `user_message` (open in browser to confirm) |
| OTP (legacy) | **OTP ref:** `session_id` and **OTP code:** `123456` (`user_message` / `feishu_user_message` from tools) |
| Price / fare monitor | **Monitor ref:** `session_id` |
| HNP shoe drop (**shoe only**) | **Drop ref:** `item_id` only (no curl in chat) |
| Flight no seats (**flight only**) | Suggest another date or route — **never** Drop ref or trigger curl |
| Product / flight line | `display_name` — not raw routing keys |

Post **`user_message`** (or **`feishu_user_message`**) verbatim in the same channel where the purchase/monitor was initiated (English). **`agent_instruction`** is internal only.

## Feishu display (human-readable product names)

Never show raw routing keys (e.g. `rt_1_1_ff16fd912e_0`) as the **Product** or **Flight** line in Feishu.

After `check_product` or `search_inventory`, use **`display_name`** / **`product_label`** / **`item_name`** from the tool result for user-facing text.

Example mandate / monitoring summary:

- **Flight:** SQ830 SIN→PVG · 2026-06-10 · Economy (from `display_name`)
- **Reference:** `rt_1_1_ff16fd912e_0` only in a secondary line if needed for support
- **Budget:** 600.00 USD · **Payment:** Card

For flights, call `search_inventory` first or pass `item_name` from matches into `register_price_monitor_tool`, `create_trusted_surface_session`, and mandate JSON.

When posting monitor status, always show currency units on **both** the current price and the cap/budget, for example `Price: 586.30 USD · Budget: 600.00 USD`. Never show a bare numeric cap such as `Cap: 200.0`.

## Trusted Surface (H5 portal — default)

Before signing mandates, show a clear **English** purchase summary (item or flight, price cap / fare, payment rail). Wait for **yes / approve / confirm**.

Then create an H5 Trusted Surface session (content is frozen server-side; the user opens a deterministic confirm page):

**HNP shoe** (`price_cap` in **USD dollars**):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=CHAT_ID price_cap=200 payment_method=card presence_mode=hnp \
  item_id=supershoe_limited_edition_gold_sneaker_womens_9_0 \
  item_name="SuperShoe Gold Womens 9"
```

**HNP flight** (`price_cap` = user budget in USD):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=CHAT_ID price_cap=600 payment_method=card presence_mode=hnp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-10 · Economy"
```

**HP** (after `create_checkout` — pass **`amount_cents`** from checkout total; must match step 6 `assemble_and_sign_immediate_mandates`):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=CHAT_ID amount_cents=50630 price_cap=506.30 payment_method=card presence_mode=hp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-10 · Economy"
```

`amount_cents` is the canonical approval key (integer cents). If you pass both, **`amount_cents` wins** — a wrong `price_cap` alone cannot cause a second portal round.

1. Post **`user_message`** to the user **verbatim**. On **WeChat**, the portal URL is a **plain URL on its own line** (WeChat bot = text only; markdown links and `localhost` are **not** clickable — user must **long-press to copy** and paste into a browser on the same computer). On **Feishu**, you may use **`feishu_user_message`** (markdown link). Remember the exact **`ref`** from the tool result.
2. **Immediately** call server-side long-poll (one tool call; blocks in Python — no LLM polling loop, no user "done" required):

```bash
mcporter call ap2-buyer.wait_for_trusted_surface_signed ref=REF_FROM_STEP_1 timeout_seconds=300
```

3. Branch on `status`:
   - **`signed`** → call `assemble_and_sign_*` on the **same `session_id`**, then continue HP/HNP steps without a new portal.
   - **`timeout`** or **`pending`** (if user interrupted) → remind them to open `portal_url` and confirm, then call `wait_for_trusted_surface_signed` again with the **same ref** (do not create a new session unless `expired`).
   - **`expired`** → call `create_trusted_surface_session` again (same `session_id`) for a fresh `ref`.

If the user sends "done" anyway, you may call `get_trusted_surface_status` once as a fallback — prefer `wait_for_trusted_surface_signed` after posting the portal.

**Never** skip the portal — budget or payment rail choice alone is **not** approval. **Never** call `get_trusted_surface_status` in a tight loop (each call costs an LLM turn).

### Legacy OTP path (only if `AP2_REQUIRE_OTP=1`)

When OTP is enabled instead of H5:

1. After user confirms, call **register** (issues OTP; does not grant approval yet):

```bash
mcporter call ap2-buyer.register_trusted_surface_approval \
  session_id=CHAT_ID price_cap=200 payment_method=card \
  item_id=supershoe_limited_edition_gold_sneaker_womens_9_0 \
  item_name="SuperShoe Gold Womens 9"
```

2. If `otp_required`, post **`user_message`** / **`feishu_user_message`** (**OTP ref** + **OTP code**) to the initiating channel. Do not tell the user to run `show_otp.sh` or any local command.

3. User sends the 6-digit code in chat. Call **verify**:

```bash
mcporter call ap2-buyer.verify_payment_otp session_id=CHAT_ID code=123456
```

4. Only after verify returns `status: ok`, call `assemble_and_sign_*`.

**Never** read `.temp-db/otp_*.json` for the code. Budget or payment rail choice alone is **not** approval.

## HNP flow (delegated purchase)

Shared steps 4–9 apply after merchant-specific setup (steps 1–3).

### Shoe (`merchant=shoe`)

1. **set_ap2_session_config** → `merchant=shoe`, `hnp`, `card` or `x402`.
2. Build `item_id` as `<slug>_0` (lowercase, non-alphanumeric → `_`). **Do not** call `search_inventory` for shoes.
3. `mcporter call ap2-merchant.check_product item_id=... constraint_price_cap=200`

### Flight (`merchant=flight`)

1. **set_ap2_session_config** → `merchant=flight`, `hnp`, `card` or `x402`.
2. **`search_inventory`** → user picks flight → `item_id`.
3. `mcporter call ap2-merchant.check_product item_id=... constraint_price_cap=<USER_BUDGET>`

**Never** build a shoe-style slug for flights. **Never** show Drop ref or trigger curl for flights.

### Shared (shoe + flight)

4. Mandate summary → confirm → `create_trusted_surface_session` → post `portal_url` → `wait_for_trusted_surface_signed` (see Trusted Surface section).
5. Sign mandates — `mandate_request` must be a **JSON string** inside `--args`:

```bash
mcporter call ap2-buyer.assemble_and_sign_mandates --args '{
  "session_id": "CHAT_ID",
  "mandate_request": "{\"item_id\":\"...\",\"price_cap\":600,\"qty\":1}"
}'
```

6. **Scheduled price monitoring** (backend scheduler on **:8105** — no OpenClaw cron):
   - **Ask the user how often to check the price/fare.** Default 5 minutes if they do not care. Minimum **1 minute**.
   - **Never modify merchant databases, HEG rows, or trigger files to force a price drop.**

```bash
mcporter call ap2-buyer.register_price_monitor_tool \
  session_id=CHAT_ID item_id=ITEM_ID price_cap=600 interval_minutes=<USER_CHOSEN_MINUTES> \
  item_name="SQ830 SIN→PVG · 2026-06-21 · Economy" merchant=flight
```

After registration: post **`feishu_user_message`** (Monitor ref). **Do not** run cron loops or manual tick scripts. Poll:

```bash
mcporter call ap2-buyer.get_price_monitor_status_tool session_id=CHAT_ID --output json
```

When `status=purchased`, post `purchase_result.purchase_complete` and call `clear_price_monitor_tool`. **If fare ≤ budget at registration, purchase runs on the first scheduler tick** (seconds).

7. **Shoe only:** if stock is 0, tell the user **Drop ref:** `item_id` only. **Skip for flights.**

**Stop on:** purchased, not found, user cancel, max ticks, or error. **Do not** re-run the HP purchase chain yourself when constraints are met — :8105 completes checkout.

## HP flow (buy now)

### Flight (`merchant=flight`)

1. **set_ap2_session_config** → `merchant=flight`, `hp`, `card` or `x402`.
2. **`search_inventory`** → user picks flight → `check_product` → `assemble_cart` with `qty` = passenger count.

### Shoe (`merchant=shoe`)

1. **set_ap2_session_config** → `merchant=shoe`, `hp`, `card` or `x402`.
2. `search_inventory` or `check_product` → `assemble_cart`.

### Shared (shoe + flight)

3. **Once:** `create_hp_open_mandates` (no `checkout_jwt` yet). Flights: `price_cap` ≥ fare + buffer.
4. `create_checkout` with `open_checkout_mandate_id` and `payment_method`.
5. Checkout summary → user **confirm** → `create_trusted_surface_session` with **`amount_cents`** = checkout total in **cents** (same value as step 6 `assemble_and_sign_immediate_mandates`). Post `portal_url` → `wait_for_trusted_surface_signed` (see Trusted Surface section). **Remember the exact `ref`** — do not guess or retype it.
6. When `wait_for_trusted_surface_signed` returns **`signed`**: call `ap2-buyer.assemble_and_sign_immediate_mandates` **once**, then **immediately** continue to step 7 on the **same `session_id`**. Do **not** call `create_trusted_surface_session` again or ask for another portal confirm.
7. **`ap2-cp.issue_payment_credential`** (`presence_mode=hp`, chain ids from step 6) → **`ap2-merchant.complete_checkout`** → **`ap2-buyer.verify_checkout_receipt_tool`** → purchase success notification → **`purchase_complete`**.

**`purchase_complete` JSON** (last in message):

```json
{"type":"purchase_complete","order_id":"...","item_id":"...","item_name":"SQ836 SIN→PVG · 2026-06-10 · Economy","total_cents":50630,"currency":"USD","payment_method":"card","status":"success","receipt":{}}
```

**Never** call `create_hp_open_mandates` twice per purchase. **Never** re-run `assemble_cart` / `create_checkout` after TS is signed. **Never** call `reset_temp_db_tool` or `clear_open_mandate_session_tool` during an in-progress HP purchase (payment-rail switch only). If a step fails, report the tool error and **retry that step only** — do not wipe state, change `session_id`, or restart from step 1.

## Payment rail switch

`set_ap2_session_config_tool` with new `payment_method` → `clear_open_mandate_session_tool` → `create_trusted_surface_session` → post `portal_url` → `wait_for_trusted_surface_signed` → sign again.

## Errors

If any tool returns `"error"`, stop and report the `message` to the user. For flight failures, verify HEG is running on `:9000`.

## Stop backend

```bash
cd "$AP2_HOME/code/samples/python/scenarios/a2a/unified" && ./openclaw/stop_ap2_backend.sh
```

## Bot verification playbook

Before Feishu/WeChat testing: start backend (`openclaw/start_ap2_backend.sh`), HEG for flights (`demo-op ap2.prereq.heg`), run `./scripts/smoke_openclaw_mcp.sh`, then optional `scripts/smoke_hnp_monitor_scheduler.py` and `scripts/e2e_flight_hnp.py`.

**Full checklist** (flows A–E, sample prompts, failure table): see **`openclaw/SKILL.md`** in the AP2 repo — section **Bot verification playbook**. Use **June 21 2026** (or later) in flight search text for HEG inventory.
