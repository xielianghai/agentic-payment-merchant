---
name: ap2-checkout
description: |
  AP2 mock shopping and checkout (reply in English only). Use first for shopping,
  buying goods, or booking flights; SuperShoe/Singapore Airlines HP/HNP,
  card or x402.
  Requires ./openclaw/start_ap2_backend.sh and HEG backend (:9000) for flights.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "🛒",
        "requires": { "bins": ["mcporter", "curl"] },
      },
  }
---

# AP2 Checkout (openclaw + mock backend)

**Language (mandatory):** All replies in **English** — summaries, status tables, errors, OTP/monitor prompts. The user may send Chinese (e.g. 开启 AP2 mock 支付); **still respond in English**. Only use Chinese if the user explicitly asks for Chinese replies.

You drive the **full AP2 purchase flow** via **mcporter** against local mock MCP servers.
All money movement is simulated — no real payments.

## User-facing messages (WeChat / Feishu)

Send **only** a clean English confirmation — product/flight, fare, payment rail, order id, and success line.

**Never** send to the user:
- `purchase_complete` JSON blocks or fenced ```json``` code
- Internal reasoning ("Let me deliver...", "Both closed mandates exist...", "Here's the notification...")
- Mandate ids (`chk_*`, `pay_*`, `open_chk_*`), JWT/SDJWT snippets, or mcporter tool logs

Keep debugging and tool output in tool calls only — not in the chat reply.

Example (flight HP success):

```
Booking confirmed!

Flight: SQ830 SIN→PVG · 2026-06-21 · Economy
Fare: 406.30 USD · Payment: Card
Order: 351018e0-907d-42f6-b690-920118cd7c58
```

## Default shopping trigger

When this skill is installed and enabled, treat **any shopping or purchase intent** as a match for this skill by default. This includes generic prompts such as **"I want to shop"**, **"I want to buy something"**, **"我要购物"**, **"我要买东西"**, as well as flight-booking prompts such as **"book a flight"** or **"我要买机票"**.

For those intents, **use AP2 mock checkout first** instead of real merchant/payment flows or other generic shopping behavior. If the user only says they want to shop, select this skill, start the AP2 mock shopping flow, and ask what they want to buy before calling merchant tools.

For **flight** intents, collect route / date / cabin / passengers / budget (HNP) **before** the first merchant tool call — do not default to shoe.

**Demo one-shot** (ClawHub skill + OpenClaw config + auto-start backend):

```bash
cd "$AP2_HOME"
npx -y file:code/samples/python/scenarios/a2a/unified/clawhub/npm/ap2-agent-checkout install
```

## Prerequisites

1. Start the AP2 mock backend (from repo):

```bash
cd code/samples/python/scenarios/a2a/unified
chmod +x openclaw/start_ap2_backend.sh openclaw/stop_ap2_backend.sh
./openclaw/start_ap2_backend.sh
```

This starts MCP HTTP (8100–8103), triggers (8091–8094), H5 Trusted Surface (8104), and HNP monitor scheduler (8105). It does **not** start the HEG flight backend.

2. **For flight booking (`merchant=flight`)**, start HEG separately (required):

```bash
cd code/samples/python/scenarios/a2a/unified
./demo-op ap2.prereq.heg
```

Default HEG API: `http://127.0.0.1:9000`. If `search_inventory` or `check_product` fails for flights, verify HEG is running before restarting the AP2 backend.

3. Point mcporter at the bundled config:

```bash
export MCPORTER_CONFIG="/path/to/AP2/code/samples/python/scenarios/a2a/unified/openclaw/mcporter.json"
```

4. Enable this skill and **mcporter** in `~/.openclaw/openclaw.json` (`skills.entries`).

## Session identity (CRITICAL)

**`session_id` = this chat user's channel peer id** (Feishu `open_id` like `ou_d422679d1e7ad702db1139fad9ad8221`, or WeChat open id like `o9cq80zGTauIPc4iObBSrueLQ1p0`).

- Use the **same** id on **every** `ap2-buyer.*` call in this chat.
- **NEVER** use `<OPEN_ID>`, `feishu-main`, `CHAT_ID`, or any literal placeholder from the examples below — substitute the real peer id.
- **NEVER** invent suffixes like `wechat_hp_card_v2` — that orphans Trusted Surface approvals and forces extra portal confirms.
- The **OTP ref** / **Monitor ref** shown to the user is this same id.

> In every command example below, **`<OPEN_ID>` is a placeholder** — replace it with the chat's real `open_id`.

List tools:

```bash
mcporter list ap2-buyer --schema
mcporter list ap2-merchant --schema
mcporter list ap2-cp --schema
```

## MCP server routing (mandatory)

| Action | Server | Example tool |
|--------|--------|----------------|
| Session, mandates, TS portal | `ap2-buyer` | `create_trusted_surface_session`, `wait_for_trusted_surface_signed`, `assemble_and_sign_*` |
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
  session_id=<OPEN_ID> presence_mode=hnp payment_method=card merchant=shoe
```

**Flight example (required for any flight booking):**

```bash
mcporter call ap2-buyer.set_ap2_session_config_tool \
  session_id=<OPEN_ID> presence_mode=hp payment_method=card merchant=flight
```

| User intent | presence_mode | payment_method |
|-------------|---------------|----------------|
| Drop / monitor / buy when price drops (shoe) or fare watch / budget booking (flight) | `hnp` | `card` or `x402` if user says crypto |
| Buy now / in stock today / book flight now | `hp` | `card` or `x402` if user says so |

```bash
mcporter call ap2-buyer.get_ap2_session_config_tool session_id=<OPEN_ID>
```

**Always read `merchant_instruction` from the result** — it is authoritative for currency, availability rules, and merchant-specific behavior. For `merchant=flight`: no shoe trigger curl, no Drop ref, no `inventory_options`; flights are available when seats exist.

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
| Budget | USD 600 | **required for HNP**; HP uses as `price_cap` reference |
| Payment | card (default) | or x402 if user says crypto |

**Sample user prompts** (use **June 21 2026** or later for HEG inventory — avoid bare "June 10", which the parser may bump to the wrong year):

- HP: `Buy Singapore Airlines SIN to PVG economy June 21 2026 for 1 adult now with card.`
- HNP: `Book SIN to PVG economy June 21 2026 for 1 adult — budget USD 750, buy when fare is acceptable.`

If `search_inventory` returns no matches, retry with an explicit future date (`June 21 2026`) before telling the user the route is unavailable.

### Search and present results

```bash
mcporter call ap2-merchant.search_inventory \
  product_description="SIN to PVG economy June 10 1 adult" \
  constraint_price_cap=600
```

Present matches as a **numbered list** using `display_name` / `product_label` (never raw routing keys as the main line):

```
1. SQ836 · SIN→PVG · 2026-06-10 · Economy · 506.30 USD · seats available
2. SQ830 · SIN→PVG · 2026-06-10 · Economy · 586.30 USD · seats available
   Reference: rt_1_1_ff16fd912e_0
```

Let the user pick an option → use that match's `item_id` for all later steps. Pass `item_name` from the match into `create_trusted_surface_session`, `register_price_monitor_tool`, and mandate JSON.

### `price_cap` rules (flights)

- **HP:** set `price_cap` ≥ current fare; add a small buffer (e.g. +10–50 USD) so checkout total stays within mandate.
- **HNP:** `price_cap` = user's budget (USD). Purchase proceeds when `current_price ≤ price_cap` **and** seats are available. **If fare is already within budget at registration time, the backend scheduler purchases on the first tick** (within seconds of `register_price_monitor_tool`) — tell the user purchase is in progress; poll `get_price_monitor_status_tool` until `status=purchased`.

### Flight checkout summary (HP — before Trusted Surface)

Use airline-style English, not generic "Product":

- **Flight:** SQ836 SIN→PVG · 2026-06-10 · Economy
- **Passengers:** 1 adult
- **Fare:** 506.30 USD
- **Payment:** Card

### Flight monitor status (HNP)

Use **fare / budget** wording — never "drop" or "Drop ref":

```
Watching fare: SQ836 SIN→PVG · 2026-06-10 · Economy
Price: 586.30 USD · Budget: 600.00 USD · Seats: available
Next check in 5 min · Monitor ref: <session_id>
```

If no seats: tell the user and suggest another date or route — **do not** wait for a trigger or show Drop ref.

### Booking confirmed (success message)

After `complete_checkout` and `verify_checkout_receipt_tool`, post to the initiating channel:

- **Booking confirmed:** `<display_name>`
- **Total:** xxx USD · **Payment:** Card / x402
- **Order ID:** from `complete_checkout`
- **Receipt:** verified (or status from verify tool)

Do **not** paste `purchase_complete` JSON into WeChat/Feishu. It is an internal artifact for logs/tests only. Optionally note the user can verify the order in HEG admin when available.

### Flight limitations (demo)

This mock covers **search → lock seats (`assemble_cart`) → pay**. It does not collect full passenger ID forms or seat maps in chat — HEG presale runs at `assemble_cart`. Do not invent PNR steps outside the normal checkout flow.

---

## Feishu user messages — refs only (mandatory)

In **Feishu chat**, never show shell commands, `mcporter`, `curl`, `cd`, `./scripts/…`, or file paths (including `.temp-db/`).

Use short **refs** the user maps to their own terminal workflow:

| Situation | Tell the user |
|-----------|----------------|
| Trusted Surface | **`portal_url`** from `user_message` (open in browser to confirm) |
| OTP (legacy) | **OTP ref:** `session_id` and **OTP code:** `123456` (from tool `user_message` / `feishu_user_message`) |
| Price / fare monitor | **Monitor ref:** `session_id` |
| HNP shoe drop (**shoe only**) | **Drop ref:** `item_id` (user triggers locally; do not paste curl) |
| Flight no seats (**flight only**) | Suggest another date or route — **never** Drop ref or trigger curl |
| Product / flight line | `display_name` — not raw routing keys |

When a tool returns **`user_message`** or legacy **`feishu_user_message`**, post that text to the user in the same channel where the purchase/monitor was initiated (English only). Use **`agent_instruction`** internally — do not copy it into the user chat.

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

Before signing mandates, show a clear **English** purchase summary (item or flight, price cap / fare, payment rail). Wait for explicit **yes / approve / confirm** in chat.

Then create an H5 Trusted Surface session (content is frozen server-side; the user opens a deterministic confirm page):

**HNP shoe** (`price_cap` in **USD dollars**):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=<OPEN_ID> price_cap=200 payment_method=card presence_mode=hnp \
  item_id=supershoe_limited_edition_gold_sneaker_womens_9_0 \
  item_name="SuperShoe Gold Womens 9"
```

**HNP flight** (`price_cap` = user budget in USD):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=<OPEN_ID> price_cap=600 payment_method=card presence_mode=hnp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-10 · Economy"
```

**HP** (after `create_checkout` — pass **`amount_cents`** from checkout total; must match step 6 `assemble_and_sign_immediate_mandates`):

```bash
mcporter call ap2-buyer.create_trusted_surface_session \
  session_id=<OPEN_ID> amount_cents=50630 price_cap=506.30 payment_method=card presence_mode=hp \
  item_id=rt_1_1_ff16fd912e_0 item_name="SQ836 SIN→PVG · 2026-06-10 · Economy"
```

`amount_cents` is the canonical approval key (integer cents). If you pass both, **`amount_cents` wins** — a wrong `price_cap` alone cannot cause a second portal round.

1. Post **`user_message`** to the user **verbatim** in the initiating channel. On **WeChat**, the portal URL is a **plain URL on its own line** (WeChat bot = text only; markdown links and `localhost` are **not** clickable — user must **long-press to copy** and paste into a browser on the same computer). On **Feishu**, you may use **`feishu_user_message`** (markdown link). Remember the exact **`ref`** from the tool result.
2. **Immediately** call server-side long-poll (one tool call; blocks in Python — no LLM polling loop, no user "done" required):

```bash
mcporter call ap2-buyer.wait_for_trusted_surface_signed ref=REF_FROM_STEP_1 timeout_seconds=300
```

3. Branch on `status`:
   - **`signed`** → call `assemble_and_sign_*` on the **same `session_id`**, then continue HP/HNP steps without a new portal. The H5 page has a **Close** button (top-right and after success) to dismiss the portal tab.
   - **HP signed** → continue the existing HP checkout on the **same `session_id`** and **same purchase state**. Do not manually reset state, create a second portal, or restart from search/cart.
   - **`timeout`** or **`pending`** (if user interrupted) → remind them to open `portal_url` and confirm, then call `wait_for_trusted_surface_signed` again with the **same ref** (do not create a new session unless `expired`).
   - **`expired`** → call `create_trusted_surface_session` again (same `session_id`) for a fresh `ref`.

If the user sends "done" anyway, you may call `get_trusted_surface_status` once as a fallback — prefer `wait_for_trusted_surface_signed` after posting the portal.

**Never** skip the portal — budget or payment rail choice alone is **not** approval. **Never** call `get_trusted_surface_status` in a tight loop (each call costs an LLM turn).

### Legacy OTP path (only if `AP2_REQUIRE_OTP=1`)

When OTP is enabled instead of H5:

1. After user confirms, call **register** (issues OTP; does **not** grant approval yet):

```bash
mcporter call ap2-buyer.register_trusted_surface_approval \
  session_id=<OPEN_ID> price_cap=200 payment_method=card \
  item_id=supershoe_limited_edition_gold_sneaker_womens_9_0 \
  item_name="SuperShoe Gold Womens 9"
```

2. If status is `otp_required`, **immediately reply in the initiating channel** with the tool's **`user_message`** / **`feishu_user_message`** (shows **OTP ref** and **OTP code**, no script paths). **Never tell the user to run `show_otp.sh` or any local command.**

3. User sends the **6-digit code** in Feishu. Call **verify**:

```bash
mcporter call ap2-buyer.verify_payment_otp session_id=<OPEN_ID> code=123456
```

4. Only after `verify_payment_otp` returns `status: ok`, proceed to `assemble_and_sign_*`.

Plain-text budget or "pay by card" alone is **not** approval.

---

## HNP flow (delegated purchase)

Shared steps 4–9 apply after merchant-specific setup (steps 1–3).

### Shoe (`merchant=shoe`)

1. **set_ap2_session_config** → `merchant=shoe`, `hnp`, `card` or `x402`.
2. Build `item_id` as `<slug>_0` (lowercase, non-alphanumeric → `_`). **Do not** call `search_inventory` for shoes.
3. `mcporter call ap2-merchant.check_product item_id=... constraint_price_cap=200`

### Flight (`merchant=flight`)

1. **set_ap2_session_config** → `merchant=flight`, `hnp`, `card` or `x402`.
2. **`search_inventory`** with route / date / cabin / pax (see Flight booking section). User picks a match → `item_id`.
3. `mcporter call ap2-merchant.check_product item_id=... constraint_price_cap=<USER_BUDGET>`

**Never** build a shoe-style slug for flights. **Never** show Drop ref, trigger curl, or `inventory_options` for flights.

### Shared (shoe + flight)

4. Mandate summary → user confirm → **create_trusted_surface_session** → post `portal_url` → **`wait_for_trusted_surface_signed`** (see Trusted Surface section).
5. `assemble_and_sign_mandates` — **`mandate_request` must be a JSON string** (mcporter will not auto-coerce objects). Use `--args`:

```bash
mcporter call ap2-buyer.assemble_and_sign_mandates --args '{
  "session_id": "<OPEN_ID>",
  "mandate_request": "{\"item_id\":\"...\",\"price_cap\":600,\"qty\":1}"
}'
```

6. **Scheduled price monitoring**:
   - **Ask the user how often to check the price/fare and wait for their reply.** Offer a default of 5 minutes if they do not care.
   - Use exactly the user's chosen interval when calling `register_price_monitor_tool`.
   - Minimum interval is **1 minute** (sub-minute values round up to 1).
   - **Never modify merchant databases, HEG MySQL rows, trigger files, or backend state to force a price drop.** The monitor must observe prices through `ap2-merchant.check_product` only.

**Shoe:**

```bash
mcporter call ap2-buyer.register_price_monitor_tool \
  session_id=<OPEN_ID> item_id=ITEM_ID price_cap=200 interval_minutes=<USER_CHOSEN_MINUTES> \
  item_name="SuperShoe Gold Womens 9" merchant=shoe
```

**Flight:**

```bash
mcporter call ap2-buyer.register_price_monitor_tool \
  session_id=<OPEN_ID> item_id=ITEM_ID price_cap=600 interval_minutes=<USER_CHOSEN_MINUTES> \
  item_name="SQ836 SIN→PVG · 2026-06-10 · Economy" merchant=flight
```

Pass `item_name` + `merchant` so the monitor card shows a readable product (not a routing key).

**Backend scheduler (required).** `register_price_monitor_tool` arms the monitor in shared session storage. The **monitor scheduler** on port **8105** (started by `start_ap2_backend.sh`) drives ticks, constraint checks, and **automatic HNP purchase** — no OpenClaw cron, `/loop`, or manual tick scripts. **`POST /monitor/register` triggers an immediate first tick** when the monitor is armed.

After registration:

1. Post the tool's **`feishu_user_message`** (Monitor ref + interval) to the initiating channel.
2. **Do not** run `monitor_cron.sh`, `monitor_price_tick.sh`, or per-tick `check_product` loops yourself.
3. Poll **`get_price_monitor_status_tool`** after registration (especially flight HNP when fare ≤ budget) until `status` is `purchased`, `stopped`, or `error`:

```bash
mcporter call ap2-buyer.get_price_monitor_status_tool session_id=<OPEN_ID> --output json
```

4. When status is **`purchased`**, post the purchase summary from `purchase_result` / `purchase_complete` and stop — the backend already completed checkout.

**Stop conditions:** constraints met (purchase runs automatically), item not found, user cancels (`clear_price_monitor_tool`), or max ticks. On any terminal status, do not re-arm the monitor.

**Changing the interval:** call `register_price_monitor_tool` again with the new `interval_minutes` and post the updated **Monitor ref** + interval.

7. Manual polling is **not** required — the backend scheduler handles ticks. Use step 6 registration only.

8. **Shoe only:** when stock is 0 (after default 5 units are sold), tell the user **Drop ref:** `item_id` only (they run their local trigger; **no curl block in chat**). **Skip this step for flights.**

9. When the backend scheduler reports **`purchased`** (via status poll or wake hook):
   - **Do not** run the purchase chain yourself — checkout already completed on :8105.
   - Post a concise purchase success notification (product/flight, total, order id, payment method).
   - Emit **`purchase_complete`** JSON from `purchase_result.purchase_complete` if present.
   - Call `clear_price_monitor_tool` to clear monitor state.

---

## HP flow (buy now, user present)

### Shoe (`merchant=shoe`)

1. **set_ap2_session_config** → `merchant=shoe`, `hp`, `card` or `x402`.
2. `check_product` with known `item_id`, or `search_inventory` if needed → `assemble_cart`.

### Flight (`merchant=flight`)

1. **set_ap2_session_config** → `merchant=flight`, `hp`, `card` or `x402`.
2. **`search_inventory`** → user picks flight → `check_product` → `assemble_cart` with `qty` = passenger count.

### Shared (shoe + flight)

3. **Once per purchase:** `ap2-buyer.create_hp_open_mandates` with `item_id`, `price_cap`, `qty`, `payment_method` (no `checkout_jwt` yet). For flights, `price_cap` ≥ fare + small buffer.
4. `ap2-merchant.create_checkout` with `cart_id`, `open_checkout_mandate_id`, `payment_method`.
5. Post checkout summary in the initiating channel (flight-style summary for flights); wait for user **confirm**. On confirm: **create_trusted_surface_session** with **`amount_cents`** = checkout total in **cents** (same value as step 6 `assemble_and_sign_immediate_mandates`). `price_cap` is optional display in USD (e.g. `amount_cents/100`). Post `portal_url` → **`wait_for_trusted_surface_signed`** (see Trusted Surface section). **Remember the exact `ref`** — do not guess or retype it.
6. When `wait_for_trusted_surface_signed` returns **`signed`**: call `ap2-buyer.assemble_and_sign_immediate_mandates` **once** with the **closed** mandate JWTs from step 4 (not the merchant cart `checkout_jwt`), then **immediately** continue to step 7 on the **same `session_id`**. Do **not** call `create_trusted_surface_session` again, do **not** ask for another portal confirm, and do **not** say "session was reset".
7. **`ap2-cp.issue_payment_credential`** (`presence_mode=hp`, chain ids from step 6) → **`ap2-merchant.complete_checkout`** → optional **`ap2-buyer.verify_checkout_receipt_tool`** → send the **user-facing confirmation** (see above — no JSON blocks, mandate ids, JWTs, or tool logs).

**`purchase_complete` JSON** is an **internal artifact** for logs/tests — **do not paste it into WeChat/Feishu**. Shape when needed for tooling only:

```json
{"type":"purchase_complete","order_id":"...","item_name":"...","total_cents":50630,"currency":"USD","payment_method":"card","status":"success"}
```

**Never** call `create_hp_open_mandates` twice per purchase. **Never** re-run `assemble_cart` / `create_checkout` after TS is signed. **Never** call `reset_temp_db_tool` or `clear_open_mandate_session_tool` during an in-progress HP purchase (payment-rail switch only). If a step fails, report the tool error and **retry that step only** — do not wipe state, change `session_id`, or restart from step 1.

---

## Payment rail switch

If the user switches card ↔ x402 after signing:

```bash
mcporter call ap2-buyer.set_ap2_session_config_tool session_id=... presence_mode=hnp payment_method=x402
mcporter call ap2-buyer.clear_open_mandate_session_tool session_id=...
```

Re-approve in the initiating channel: **create_trusted_surface_session** → post `portal_url` → **`wait_for_trusted_surface_signed`** → sign again.

## x402 notes

- Use `payment_method=x402` on merchant, buyer, and CP tools.
- x402 settlement uses mock Base Sepolia USDC (demo keys in `.temp-db`).
- Same flows as card; instrument constraints are embedded in open payment mandates.

## Errors

If any tool returns `"error"`, stop and report the `message` to the user. Check `.logs/*-mcp-http.log` under the unified scenario directory. For flight search/checkout failures, also verify HEG is running on `:9000`.

## Stop backend

```bash
./openclaw/stop_ap2_backend.sh
```

---

## Bot verification playbook (operator + Feishu/WeChat)

Use this before asking users to test in the bot. **Do not run `ap2.unified.web` and openclaw backend at the same time** (shared ports 8091–8094, 8104–8105).

### 1. Terminal pre-check (from unified scenario root)

```bash
cd code/samples/python/scenarios/a2a/unified
./openclaw/stop_ap2_backend.sh    # if anything was running
./demo-op ap2.prereq.heg           # required for flight flows
./openclaw/start_ap2_backend.sh
export MCPORTER_CONFIG="$PWD/openclaw/mcporter.json"
./scripts/smoke_openclaw_mcp.sh      # buyer + merchant + H5 TS + assemble
curl -sf http://127.0.0.1:8105/health
uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py   # shoe HNP → purchase
uv run --no-sync python scripts/e2e_flight_hnp.py                # flight HNP → immediate purchase when fare ≤ budget
```

Optional full matrix (requires **`./start.sh` web stack**, not openclaw): `./scripts/run_e2e_all.sh`

### 2. Flows to exercise in the bot

Use the chat user's real **`open_id`** as `session_id` on every tool call. Reply in **English** in the channel.

| # | Flow | Example user message | What you must do | Success signal |
|---|------|----------------------|------------------|----------------|
| A | Shoe HNP + card | `When is the SuperShoe Gold women's size 9 drop? Budget USD 700, card.` | `set_ap2_session_config` shoe/hnp/card → `check_product` → TS portal → `assemble_and_sign_mandates` → `register_price_monitor_tool` merchant=shoe → tell user **Drop ref** → poll status after they trigger drop locally | `get_price_monitor_status` → `purchased` + `purchase_complete` |
| B | Shoe HNP + x402 | Same + `pay with x402` | Same with `payment_method=x402` | Same |
| C | Flight HNP + card | `Book SIN to PVG economy June 21 2026, 1 adult, budget USD 750, card.` | `set_ap2_session_config` flight/hnp/card → `search_inventory` → user picks flight → TS → assemble → `register_price_monitor_tool` merchant=flight → **poll status** (no Drop ref) | `purchased` within ~30s if fare ≤ budget |
| D | Flight HP + card | `Buy Singapore Airlines SIN to PVG economy June 21 2026 for 1 adult now with card.` | flight/hp/card → search → cart → HP open mandates → checkout → TS with `amount_cents` → CP credential → `complete_checkout` | `purchase_complete` JSON + order id |
| E | Shoe HP + card | `Buy SuperShoe Gold size 9 women now with card.` | shoe/hp/card → check_product (in stock or after user drop) → HP chain | `purchase_complete` |

### 3. Common bot failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Flight search empty | HEG not running or date in the past | `./demo-op ap2.prereq.heg`; use **June 21 2026** in search text |
| Signed mandate but no purchase (flight) | Monitor not registered or wrong merchant | Call `register_price_monitor_tool` with `merchant=flight`; poll `get_price_monitor_status_tool` |
| `Unknown tool` on payment | Wrong MCP server | `issue_payment_credential` → **`ap2-cp`** only |
| Second portal after HP sign | New TS session or wrong ref | Reuse same `ref`; pass `amount_cents` from checkout total |
| Monitor stuck | Scheduler not on :8105 | Restart `./openclaw/start_ap2_backend.sh`; check `.logs/monitor-scheduler.log` |

### 4. Logs

```text
code/samples/python/scenarios/a2a/unified/.logs/
  buyer-mcp-http.log  merchant-mcp-http.log  monitor-scheduler.log  trusted-surface.log
```

Temp session state: `.temp-db/session_<open_id>.json` (openclaw backend uses `.run-openclaw` pid file; temp DB path printed at startup).
