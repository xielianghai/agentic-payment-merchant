#!/usr/bin/env python3
"""E2E: Flight HNP — register monitor → scheduler purchase (no shoe trigger).

Requires demo stack (:8105 scheduler, HEG :9000).

Usage (from unified/):
  uv run --no-sync python scripts/e2e_flight_hnp.py
  PAYMENT_METHOD=x402 uv run --no-sync python scripts/e2e_flight_hnp.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import parse, request

_UNIFIED = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED
_AGENT = _UNIFIED / "shopping_agent_unified"

sys.path.insert(0, str(_UNIFIED))
from path_setup import ensure_src_on_path, resolve_heg_mcp_server  # noqa: E402

_SAMPLES_SRC = ensure_src_on_path()
_HEG_MCP = resolve_heg_mcp_server()

os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED / ".temp-db"))
os.environ.setdefault("AP2_DISABLE_TS_GATE", "1")
os.environ.setdefault("HEG_FLIGHT_BACKEND_URL", "http://127.0.0.1:9000")
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT), str(_ROLES)]

from trusted_surface_gate import grant_trusted_surface_approval, reset_request_session_id  # noqa: E402

from buyer_mcp_unified.session_store import load_tool_context  # noqa: E402
from shopping_agent.agent import set_ap2_session_config  # noqa: E402
from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool  # noqa: E402

SCHEDULER_URL = os.environ.get(
    "MONITOR_SCHEDULER_URL", "http://127.0.0.1:8105"
).rstrip("/")
POLL_TIMEOUT_S = int(os.environ.get("SMOKE_MONITOR_TIMEOUT_S", "120"))
POLL_INTERVAL_S = float(os.environ.get("SMOKE_MONITOR_POLL_S", "3"))
PAYMENT_METHOD = (os.environ.get("PAYMENT_METHOD", "card").strip().lower() or "card")
if PAYMENT_METHOD not in ("card", "x402"):
  PAYMENT_METHOD = "card"


def _http_json(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = request.Request(url, data=data, headers=headers, method=method)
  with request.urlopen(req, timeout=30) as resp:
    raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _load_heg_mcp():
  spec = importlib.util.spec_from_file_location("heg_flight_mcp", _HEG_MCP)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load HEG MCP from {_HEG_MCP}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


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
      "merchant": "flight",
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
  return _http_json("GET", f"{SCHEDULER_URL}/monitor/status?{qs}")


async def _resolve_flight_item(heg, search_query: str, budget: float) -> tuple[str, float, str]:
  search = await heg.search_inventory(search_query, constraint_price_cap=budget)
  if search.get("error"):
    raise SystemExit(f"search_inventory failed: {search}")
  matches = search.get("matches") or []
  if not matches:
    raise SystemExit(f"no flight matches for {search_query!r}")
  item = matches[0]
  item_id = str(item["item_id"])
  price = float(item["price"])
  name = str(item.get("name", item_id))
  check = await heg.check_product(item_id, constraint_price_cap=budget)
  if check.get("error") or not check.get("available"):
    raise SystemExit(f"flight not available: {check}")
  if price > budget:
    raise SystemExit(
        f"fare ${price} exceeds budget ${budget}; raise E2E_FLIGHT_HNP_BUDGET"
    )
  return item_id, price, name


def main() -> None:
  health = _http_json("GET", f"{SCHEDULER_URL}/health")
  if health.get("status") != "ok":
    raise SystemExit(f"scheduler unhealthy: {health}")

  search_query = os.environ.get(
      "E2E_FLIGHT_SEARCH", "SIN to PVG economy July 21 2026 1 adult"
  )
  budget = float(os.environ.get("E2E_FLIGHT_HNP_BUDGET", "600"))

  heg = _load_heg_mcp()
  item_id, price, item_name = asyncio.run(
      _resolve_flight_item(heg, search_query, budget)
  )

  session_id = f"e2e_flight_hnp_{uuid.uuid4().hex[:10]}"
  print(f"session_id={session_id} item_id={item_id} price={price} cap={budget}")

  token = grant_trusted_surface_approval(budget, PAYMENT_METHOD, session_id=session_id)
  try:
    ctx = load_tool_context(session_id)
    cfg = set_ap2_session_config("hnp", PAYMENT_METHOD, ctx, merchant="flight")
    if cfg.get("error"):
      raise SystemExit(f"set_ap2_session_config failed: {cfg}")

    mandate_request = json.dumps({
        "item_id": item_id,
        "item_name": item_name,
        "price_cap": budget,
        "qty": 1,
        "constraint_focus": "price",
        "available": True,
    })
    signed = assemble_and_sign_mandates_tool(mandate_request, ctx)
    if signed.get("error"):
      raise SystemExit(f"assemble_and_sign failed: {signed}")

    checkout_id = str(signed.get("open_checkout_mandate", ""))
    payment_id = str(signed.get("open_payment_mandate", ""))
    reg = _register_monitor(
        session_id,
        item_id=item_id,
        price_cap=budget,
        checkout_id=checkout_id,
        payment_id=payment_id,
        checkout_hash=str(signed.get("open_checkout_hash") or "") or None,
    )
    if reg.get("status") != "ok":
      raise SystemExit(f"monitor register failed: {reg}")
    print("OK  register flight HNP monitor")

    deadline = time.time() + POLL_TIMEOUT_S
    last_status: dict[str, Any] = {}
    while time.time() < deadline:
      last_status = _monitor_status(session_id)
      status = str(last_status.get("status", ""))
      tick = last_status.get("monitoring") or {}
      print(
          f"  poll status={status} price={tick.get('current_price')} "
          f"meets={tick.get('meets_constraints')}",
      )
      if status == "purchased":
        pc = last_status.get("purchase_complete") or {}
        order_id = pc.get("order_id")
        print(f"OK  e2e_flight_hnp PASSED order_id={order_id} rail={PAYMENT_METHOD}")
        return
      if status == "stopped":
        raise SystemExit(f"monitor stopped: {last_status}")
      time.sleep(POLL_INTERVAL_S)

    raise SystemExit(f"timeout; last={last_status}")
  finally:
    reset_request_session_id(token)


if __name__ == "__main__":
  main()
