# H5 Trusted Surface (standalone role)

Standalone AP2 **Trusted Surface** service for the unified demo. Separate from **Credential Provider** (CP holds the user public key and verifies mandates; TS holds the user signing key and records explicit approval).

## Quick start

Started automatically by:

- `./start.sh` (web UI path)
- `agent-skill/qclaw/heg-flight/scripts/start-backend.sh` (QClaw buyer MCP path)

Default URL: **http://localhost:8104/**

## Flow

1. Shopping agent (via buyer MCP) calls `create_trusted_surface_session` with the mandate draft.
2. TS freezes the draft and returns `{ ref, portal_url }`.
3. Agent shows `portal_url` to the user (clickable link).
4. User opens `GET /ts/confirm?ref=...`, reviews the frozen summary, authorizes with **passkey** (Touch ID / Windows Hello). First visit auto-registers a passkey; later visits authenticate. Optional PIN fallback when `TS_PIN` is set.
5. Agent polls `get_trusted_surface_status` until `status: signed`.
6. Agent continues `assemble_and_sign_*` → checkout.

Passkey challenges are bound to the frozen mandate (`SHA-256` of canonical draft fields) so authorization is cryptographically tied to what the user sees.

## HTTP endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/ts/sessions` | Freeze draft, return `portal_url` |
| GET | `/ts/confirm?ref=` | H5 confirmation page |
| GET | `/ts/mandate?ref=` | Authoritative frozen draft (JSON) |
| GET | `/ts/passkey/options?ref=` | WebAuthn register/auth options (mandate-bound challenge) |
| POST | `/ts/passkey/register` | Verify passkey registration + record approval |
| POST | `/ts/passkey/verify` | Verify passkey assertion + record approval |
| POST | `/ts/approve` | PIN fallback confirm (`{ ref, pin? }`) |
| GET | `/ts/status?ref=` | `pending` \| `signed` \| `expired` |

## Buyer MCP tools

- `create_trusted_surface_session` — create session, get `portal_url`
- `get_trusted_surface_status` — poll by `ref`

Legacy OTP tools (`register_trusted_surface_approval`, `verify_payment_otp`) remain when `AP2_REQUIRE_OTP=1`.

## Environment

| Variable | Default | Notes |
|----------|---------|-------|
| `UNIFIED_TRUSTED_SURFACE_PORT` | `8104` | HTTP port |
| `TS_BASE_URL` | `http://localhost:8104` | Base URL embedded in `portal_url` (must use `localhost`, not IP, for WebAuthn) |
| `TS_RP_ID` | `localhost` | WebAuthn Relying Party ID |
| `TS_RP_NAME` | `AP2 Trusted Surface` | WebAuthn RP display name |
| `TS_ORIGIN` | `http://localhost:8104` | Expected WebAuthn origin |
| `TS_PIN` | (empty) | If set, H5 page shows PIN fallback on confirm |
| `AP2_TS_H5` | `1` | H5 path enabled |
| `AP2_REQUIRE_OTP` | `0` | Legacy Feishu OTP when `1` |
| `TEMP_DB_DIR` | `.temp-db/` | Stores `ts_sessions.json`, `ts_passkeys.json`, approvals |

## Reachability

| Scenario | URL |
|----------|-----|
| Same machine (desktop demo) | `http://localhost:8104/ts/confirm?ref=...` |
| Phone on same LAN | Passkey requires HTTPS + domain; not supported in this demo |
| WeChat in-app webview | Requires public HTTPS + domain whitelist (not in this pass) |

**Important:** Open the portal at `http://localhost:8104`, not `http://127.0.0.1:8104`. WebAuthn RP ID cannot be an IP address.

## Verification

You do **not** need a full checkout or real payment to verify passkey authorization. The `ref` in the portal URL must come from `POST /ts/sessions` or the agent's `create_trusted_surface_session` — a hand-written value like `ref=123` will show **Session not found or expired**.

### Prerequisites

1. TS server is running on port **8104** (via `./start.sh` or `python server.py` in this directory).
2. Browser supports WebAuthn (Chrome / Safari / Edge on macOS or Windows).
3. Open links at **`http://localhost:8104`**, not `127.0.0.1`.

If port 8104 is already in use:

```bash
lsof -ti:8104 | xargs kill -9
```

### Level 1 — Passkey only (fastest, no agent)

Use this to verify the H5 portal and passkey flow in isolation.

**Step 1 — Create a frozen TS session**

```bash
curl -s -X POST http://localhost:8104/ts/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "demo-user-1",
    "price_cap": 99.5,
    "payment_method": "card",
    "item_name": "Demo Shoe",
    "presence_mode": "hp"
  }'
```

Copy `portal_url` or `ref` from the JSON response. Sessions expire in **300 seconds**.

**Step 2 — Open the portal**

Open the returned URL in your browser, for example:

`http://localhost:8104/ts/confirm?ref=<ref>`

You should see the frozen mandate (product, price cap, payment method, mode).

**Step 3 — Authorize with passkey**

Click **Confirm with passkey**. Complete Touch ID / Windows Hello when prompted.

- **First visit** for this `session_id`: registers a passkey and records approval in one step.
- **Later visits**: authenticates with the existing passkey.

**Step 4 — Confirm signed status**

```bash
curl -s "http://localhost:8104/ts/status?ref=<ref>"
```

Expected: `"status": "signed"`.

Passkey verification is complete at this step — no payment or agent checkout required.

**Optional — Inspect passkey options**

```bash
curl -s "http://localhost:8104/ts/passkey/options?ref=<ref>"
```

Expected: `"op": "register"` (first time) or `"op": "auth"` (returning user), with a `publicKey` object whose `challenge` is bound to the frozen mandate.

### Level 2 — Web demo (agent generates portal URL)

Use this to verify the agent → TS → passkey → status polling path without completing payment.

1. From the scenario root, run `./start.sh`.
2. Open the web UI (default `http://localhost:5173`).
3. Start an **HP** or **HNP** flow (e.g. buy now or approve & sign).
4. When the agent posts a Trusted Surface link, open it at `http://localhost:8104/ts/confirm?ref=...`.
5. Complete passkey authorization on the portal.
6. Return to chat — the agent should detect `signed` and continue (assemble mandate, etc.).

You can stop after the portal shows **Signed** and `/ts/status` returns `signed`; finishing checkout is optional for passkey validation.

### Level 3 — Full E2E (optional)

Only needed when validating the entire chain: passkey → TS approval → `assemble_and_sign_*` → CP credential → merchant checkout → receipt.

Run Level 2 and let the agent complete the purchase through to receipt.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| **Session not found or expired** | Invalid or expired `ref` (e.g. `ref=123`) | Create a new session with `POST /ts/sessions` or restart the agent flow |
| Passkey prompt does not appear | Opened `127.0.0.1` instead of `localhost` | Use `http://localhost:8104/...` |
| **Address already in use** on `python server.py` | Another TS instance on 8104 | `lsof -ti:8104 \| xargs kill -9`, or use the instance started by `./start.sh` |
| Passkey works but agent does not continue | Agent not polling `/ts/status` | Use Level 2 (web demo) or call `wait_for_trusted_surface_signed` from buyer MCP |

Registered passkeys are stored in `.temp-db/ts_passkeys.json`. Delete that file to force re-registration for testing.

## Future work

- Inject passkey assertion evidence into AP2 PaymentMandate SD-JWT signing (currently passkey gates TS approval only).
- WeChat Mini Program + SOTER biometric, 小程序码/URL Link launch, and 公众号 gateway require a real WeChat appid and are out of scope for this H5-only pass.
