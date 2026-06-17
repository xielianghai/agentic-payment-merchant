#!/usr/bin/env python3
"""E2E: SuperShoe HP checkout (card or x402) via merchant MCP + mandates.

Requires demo stack (:8091 trigger, :8092 CP, :8093/:8094 PSP).

Usage:
  uv run --no-sync python scripts/e2e_shoe_hp.py
  PAYMENT_METHOD=x402 uv run --no-sync python scripts/e2e_shoe_hp.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import parse, request

_UNIFIED = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED / "roles"
_AGENT = _ROLES / "shopping_agent_unified"
_SAMPLES_SRC = _UNIFIED.parents[2] / "src"
_SHOE_MCP = _ROLES / "merchant_unified" / "server.py"

os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED / ".temp-db"))
os.environ.setdefault("AP2_TOKEN_STORE_PATH", str(_UNIFIED / ".temp-db" / "ap2_token_store.json"))
os.environ.setdefault(
    "MERCHANT_PAYMENT_PROCESSOR_URL", "http://127.0.0.1:8093/initiate-payment"
)
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT), str(_ROLES)]

PAYMENT_METHOD = (os.environ.get("PAYMENT_METHOD", "card").strip().lower() or "card")
if PAYMENT_METHOD not in ("card", "x402"):
  PAYMENT_METHOD = "card"
if PAYMENT_METHOD == "x402":
  os.environ["FLOW"] = "x402"
  os.environ.setdefault(
      "MERCHANT_PAYMENT_PROCESSOR_URL",
      f"http://127.0.0.1:{os.environ.get('UNIFIED_X402_PSP_TRIGGER_PORT', '8094')}/initiate-payment",
  )

TRIGGER_URL = os.environ.get(
    "MERCHANT_TRIGGER_URL",
    f"http://127.0.0.1:{os.environ.get('UNIFIED_MERCHANT_TRIGGER_PORT', '8091')}",
).rstrip("/")


class _State(dict):
  pass


class _ToolContext:
  def __init__(self) -> None:
    self.state = _State({
        "ap2:payment_method": PAYMENT_METHOD,
        "ap2:presence_mode": "hp",
        "ap2:merchant": "shoe",
    })


def _load_shoe_mcp():
  spec = importlib.util.spec_from_file_location("shoe_merchant_mcp", _SHOE_MCP)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load shoe MCP from {_SHOE_MCP}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def _trigger_in_stock(item_id: str, price: float) -> None:
  params = parse.urlencode({"item_id": item_id, "price": str(price), "stock": "10"})
  req = request.Request(
      f"{TRIGGER_URL}/trigger-price-drop?{params}",
      method="POST",
      headers={"Accept": "application/json"},
  )
  with request.urlopen(req, timeout=15) as resp:
    body = json.loads(resp.read().decode("utf-8"))
  if not body.get("ok"):
    raise SystemExit(f"trigger-price-drop failed: {body}")


def _step(name: str, result: dict) -> dict:
  if isinstance(result, dict) and result.get("error"):
    raise SystemExit(f"FAIL {name}: {result}")
  print(f"OK  {name}")
  return result


async def main() -> None:
  from shopping_agent.mandate_tools_hp import (
      assemble_and_sign_immediate_mandates_tool,
      create_hp_open_mandates_tool,
  )
  from shopping_agent.merchant_profile import apply_mandate_overrides, get_merchant_profile
  from trusted_surface_gate import (
      confirm_trusted_surface_approval,
      create_ts_session,
      set_request_session_id,
  )

  profile = get_merchant_profile("shoe")
  apply_mandate_overrides(profile)

  shoe = _load_shoe_mcp()
  search_desc = os.environ.get(
      "E2E_SHOE_SEARCH",
      "SuperShoe limited edition Gold sneaker size 9 women",
  )
  price_cap = float(os.environ.get("E2E_SHOE_HP_CAP", "250"))

  search = _step(
      "search_inventory",
      shoe.search_inventory(search_desc, constraint_price_cap=price_cap),
  )
  matches = search.get("matches") or []
  if not matches:
    raise SystemExit(f"no shoe matches: {search}")
  item = matches[0]
  item_id = str(item["item_id"])
  trigger_price = float(os.environ.get("E2E_SHOE_TRIGGER_PRICE", "199"))
  _trigger_in_stock(item_id, trigger_price)
  print(f"OK  trigger in-stock item_id={item_id} price={trigger_price}")

  check = _step(
      "check_product",
      shoe.check_product(item_id, constraint_price_cap=price_cap, payment_method=PAYMENT_METHOD),
  )
  if not check.get("available"):
    raise SystemExit(f"item not available after trigger: {check}")

  cart = _step("assemble_cart", shoe.assemble_cart(item_id, 1))
  cart_id = cart["cart_id"]
  total_minor = int(cart["total"])

  ctx = _ToolContext()
  open_m = _step(
      "create_hp_open_mandates",
      create_hp_open_mandates_tool(
          json.dumps({
              "item_id": item_id,
              "price_cap": price_cap,
              "qty": 1,
              "payment_method": PAYMENT_METHOD,
          }),
          ctx,
      ),
  )
  open_checkout_id = open_m["open_checkout_mandate_id"]

  checkout = _step(
      "create_checkout",
      shoe.create_checkout(cart_id, open_checkout_id, payment_method=PAYMENT_METHOD),
  )
  checkout_jwt = checkout["checkout_jwt"]
  checkout_jwt_hash = checkout["checkout_jwt_hash"]

  ts_session_id = f"e2e-shoe-hp-{uuid.uuid4()}"
  ts = _step(
      "create_trusted_surface_session",
      create_ts_session(
          ts_session_id,
          price_cap=price_cap,
          payment_method=PAYMENT_METHOD,
          item_id=item_id,
          item_name=str(item.get("name", item_id)),
          presence_mode="hp",
          amount_cents=total_minor,
      ),
  )
  _step(
      "confirm_trusted_surface_approval",
      confirm_trusted_surface_approval(ts["ref"], pin=os.environ.get("TS_PIN") or None),
  )
  set_request_session_id(ts_session_id)

  immediate = _step(
      "assemble_and_sign_immediate_mandates",
      assemble_and_sign_immediate_mandates_tool(
          json.dumps({
              "checkout_jwt": checkout_jwt,
              "checkout_jwt_hash": checkout_jwt_hash,
              "amount_cents": total_minor,
              "item_id": item_id,
              "price_cap": price_cap,
              "qty": 1,
              "payment_method": PAYMENT_METHOD,
              "payee": profile.merchant.model_dump(exclude_none=True),
          }),
          ctx,
      ),
  )

  from credentials_provider_unified import server as cp_server

  cred = _step(
      "issue_payment_credential",
      cp_server.issue_payment_credential(
          payment_method=PAYMENT_METHOD,
          payment_mandate_chain_id=immediate["payment_mandate_chain_id"],
          open_checkout_hash=open_m["open_checkout_hash"],
          checkout_jwt_hash=checkout_jwt_hash,
          payment_nonce=immediate["payment_nonce"],
          presence_mode="hp",
      ),
  )

  done = _step(
      "complete_checkout",
      await shoe.complete_checkout(
          payment_token=cred["payment_token"],
          checkout_mandate_id=immediate["checkout_mandate_chain_id"],
          checkout_nonce=immediate["checkout_nonce"],
          payment_method=PAYMENT_METHOD,
      ),
  )
  order_id = done.get("order_id")
  print("")
  print(f"E2E shoe HP+{PAYMENT_METHOD} PASSED order_id={order_id}")


if __name__ == "__main__":
  asyncio.run(main())
