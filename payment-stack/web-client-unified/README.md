# Web client (ADK unified demo)

React + Vite chat UI for the unified shopping agent (`:8090`). Trusted Surface approvals route through the standalone H5 server on port **8104**.

## Trusted Surface (H5 portal)

**Approve & Sign** (HNP) and **Confirm & pay** (HP) no longer sign inline in the chat card. They:

1. `POST /ts/sessions` on the TS server with the A2A `session_id` (from `localStorage` / `a2aClient.getSessionId()`)
2. Open the returned `portal_url` (new tab + link in the card)
3. Poll `GET /ts/status?ref=` until `signed`
4. Dispatch `mandate_approved` or `immediate_checkout_approved` to the agent

The portal is the non-agentic confirmation surface; the chat message is only the proceed signal.

Passkey authorization (Touch ID / Windows Hello) runs on the H5 portal. See [Trusted Surface verification](../trusted_surface_unified/README.md#verification) — Level 2 covers web demo; Level 1 can test passkey alone without a full checkout.

## HNP price monitoring

When the agent emits a **monitoring** artifact, the web client arms the backend scheduler on **8105** (`POST /monitor/register` with open mandate ids) and polls `GET /monitor/status` every 5s for UI updates. Ticks and automatic purchase are handled by the server — the client no longer sends `check_product_now` on a timer.

See [monitor scheduler README](../monitor_scheduler_unified/README.md).

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_AGENT_URL` | `/a2a/shopping_agent` | Shopping agent (Vite proxy → 8090) |
| `VITE_TS_BASE_URL` | `http://localhost:8104` | H5 Trusted Surface |
| `VITE_MONITOR_SCHEDULER_URL` | `http://localhost:8105` | Backend HNP monitor scheduler |
| `VITE_MERCHANT_TRIGGER_URL` | `http://localhost:8091` | Shoe drop trigger |
| `VITE_MERCHANT_PROFILE` | `shoe` | `shoe` or `flight` |

Start the full stack with **`ap2.unified.web`** from the scenario root (`start.sh` starts `:8104`, `:8105`, and sets `TS_BASE_URL` for the TS process).

## Dev

```bash
cd roles/web-client-unified
npm install
npm run dev    # port 5183
npm run build  # typecheck + production bundle
```

## Key files

- `src/trustedSurface.ts` — `confirmViaPortal()` (session create + poll)
- `src/components/MandateApproval.tsx` — HNP approval UI
- `src/components/ImmediateCheckoutApproval.tsx` — HP approval UI
- `src/hooks/useChat.ts` — exposes `sessionId`, dispatches approval payloads
