#!/usr/bin/env python3
"""Live E2E smoke: HNP monitor register → trigger drop → backend purchase.

Requires the unified demo stack (at least :8105 scheduler, :8091 shoe trigger).
Mandates are assembled in-process; monitor is armed via HTTP like the web client.

Usage (from unified/):
  uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py
  MONITOR_SCHEDULER_URL=http://127.0.0.1:8105 uv run --no-sync python scripts/smoke_hnp_monitor_scheduler.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

_UNIFIED = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED / "roles"
_AGENT = _ROLES / "shopping_agent_unified"
_SAMPLES_SRC = _UNIFIED.parents[2] / "src"

os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED / ".temp-db"))
os.environ.setdefault("AP2_DISABLE_TS_GATE", "1")
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT), str(_ROLES)]

from trusted_surface_gate import grant_trusted_surface_approval, reset_request_session_id  # noqa: E402

from buyer_mcp_unified.session_store import load_tool_context  # noqa: E402
from shopping_agent.agent import set_ap2_session_config  # noqa: E402
from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool  # noqa: E402

SCHEDULER_URL = os.environ.get(
    "MONITOR_SCHEDULER_URL",
    os.environ.get("MONITOR_SCHEDULER_BASE_URL", "http://127.0.0.1:8105"),
).rstrip("/")
TRIGGER_URL = os.environ.get(
    "MERCHANT_TRIGGER_URL",
    f"http://127.0.0.1:{os.environ.get('UNIFIED_MERCHANT_TRIGGER_PORT', '8091')}",
).rstrip("/")
POLL_TIMEOUT_S = int(os.environ.get("SMOKE_MONITOR_TIMEOUT_S", "90"))
POLL_INTERVAL_S = float(os.environ.get("SMOKE_MONITOR_POLL_S", "3"))
PAYMENT_METHOD = (os.environ.get("SMOKE_PAYMENT_METHOD", "card").strip().lower()
                  or "card")
if PAYMENT_METHOD not in ("card", "x402"):
  PAYMENT_METHOD = "card"


def _http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = request.Request(url, data=data, headers=headers, method=method)
  try:
    with request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read().decode("utf-8")
      return json.loads(raw) if raw else {}
  except error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    try:
      parsed = json.loads(detail)
    except json.JSONDecodeError:
      parsed = {"error": detail or exc.reason}
    parsed.setdefault("http_status", exc.code)
    return parsed


def _require_scheduler() -> None:
  health = _http_json("GET", f"{SCHEDULER_URL}/health", timeout=10)
  if health.get("status") != "ok":
    raise SystemExit(
        f"Monitor scheduler not healthy at {SCHEDULER_URL}/health: {health}"
    )


def _trigger_drop(item_id: str, price: float, stock: int = 10) -> dict[str, Any]:
  params = parse.urlencode({
      "item_id": item_id,
      "price": str(price),
      "stock": str(stock),
  })
  return _http_json("POST", f"{TRIGGER_URL}/trigger-price-drop?{params}", timeout=15)


def _register_monitor(
    session_id: str,
    *,
    item_id: str,
    price_cap: float,
    checkout_id: str,
    payment_id: str,
    checkout_hash: str | None,
) -> dict[str, Any]:
  payload: dict[str, Any] = {
      "session_id": session_id,
      "item_id": item_id,
      "price_cap": price_cap,
      "interval_minutes": int(os.environ.get("MONITOR_INTERVAL_MINUTES", "1")),
      "merchant": "shoe",
      "qty": 1,
      "open_checkout_mandate": checkout_id,
      "open_payment_mandate": payment_id,
      "payment_method": PAYMENT_METHOD,
  }
  if checkout_hash:
    payload["open_checkout_hash"] = checkout_hash
  return _http_json("POST", f"{SCHEDULER_URL}/monitor/register", payload)


def _monitor_status(session_id: str) -> dict[str, Any]:
  qs = parse.urlencode({"session_id": session_id})
  return _http_json("GET", f"{SCHEDULER_URL}/monitor/status?{qs}", timeout=15)


def main() -> None:
  _require_scheduler()

  session_id = f"smoke_hnp_{uuid.uuid4().hex[:12]}"
  item_id = "smoke_hnp_supershoe_0"
  price_cap = 200.0
  trigger_price = 150.0

  print(f"session_id={session_id}")
  print(f"scheduler={SCHEDULER_URL} trigger={TRIGGER_URL} rail={PAYMENT_METHOD}")

  token = grant_trusted_surface_approval(
      int(price_cap), PAYMENT_METHOD, session_id=session_id
  )
  try:
    ctx = load_tool_context(session_id)
    cfg = set_ap2_session_config("hnp", PAYMENT_METHOD, ctx, merchant="shoe")
    if cfg.get("error"):
      raise SystemExit(f"set_ap2_session_config failed: {cfg}")

    mandate_request = json.dumps({
        "item_id": item_id,
        "item_name": "Smoke HNP SuperShoe",
        "price_cap": price_cap,
        "qty": 1,
    })
    signed = assemble_and_sign_mandates_tool(mandate_request, ctx)
    if signed.get("error"):
      raise SystemExit(f"assemble_and_sign failed: {signed}")

    checkout_id = str(signed.get("open_checkout_mandate", ""))
    payment_id = str(signed.get("open_payment_mandate", ""))
    if not checkout_id.startswith("open_chk_") or not payment_id.startswith("open_pay_"):
      raise SystemExit(f"unexpected assemble ids: {signed}")

    reg = _register_monitor(
        session_id,
        item_id=item_id,
        price_cap=price_cap,
        checkout_id=checkout_id,
        payment_id=payment_id,
        checkout_hash=str(signed.get("open_checkout_hash") or "") or None,
    )
    if reg.get("status") != "ok":
      raise SystemExit(f"monitor register failed: {reg}")
    print(f"OK  register driver={reg.get('driver')} item_id={reg.get('item_id')}")

    active = _monitor_status(session_id)
    if active.get("status") not in ("active", "purchasing"):
      raise SystemExit(f"expected active monitor, got: {active}")

    drop = _trigger_drop(item_id, trigger_price, stock=10)
    if not drop.get("ok"):
      raise SystemExit(f"trigger-price-drop failed: {drop}")
    print(f"OK  trigger drop price=${trigger_price} item_id={item_id}")

    deadline = time.time() + POLL_TIMEOUT_S
    last_status = active
    while time.time() < deadline:
      last_status = _monitor_status(session_id)
      status = str(last_status.get("status", ""))
      tick = last_status.get("monitoring") or {}
      print(
          f"  poll status={status} price={tick.get('current_price')} "
          f"available={tick.get('available')} meets={tick.get('meets_constraints')}",
      )
      if status == "purchased":
        pc = last_status.get("purchase_complete") or {}
        order_id = pc.get("order_id") or last_status.get("purchase_result", {}).get(
            "order_id"
        )
        print(f"OK  smoke_hnp_monitor_scheduler: purchased order_id={order_id}")
        return
      if status == "stopped":
        raise SystemExit(
            f"monitor stopped: {last_status.get('stop_reason')} — {last_status}"
        )
      time.sleep(POLL_INTERVAL_S)

    raise SystemExit(
        f"timeout after {POLL_TIMEOUT_S}s waiting for purchase; last={last_status}"
    )
  finally:
    reset_request_session_id(token)


if __name__ == "__main__":
  main()
