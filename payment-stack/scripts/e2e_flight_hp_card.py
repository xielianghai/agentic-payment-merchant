#!/usr/bin/env python3
"""E2E: Singapore Airlines flight booking (HP + card) via HEG MCP + mandates.

Exercises the same tool chain the shopping agent uses, without an LLM:
  search_inventory → check_product → assemble_cart → create_hp_open_mandates
  → create_checkout → assemble_and_sign_immediate_mandates → issue_payment_credential
  → complete_checkout → verify HEG order

Requires:
  - HEG backend on :9000
  - Unified CP/MPP triggers on :8092/:8093 (./start.sh with UNIFIED_MERCHANT=flight)

Usage:
  cd code/samples/python/scenarios/a2a/unified
  UNIFIED_MERCHANT=flight uv run --no-sync --package ap2-samples \\
    python scripts/e2e_flight_hp_card.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

_UNIFIED_ROOT = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED_ROOT / "roles"
_AGENT_DIR = _ROLES / "shopping_agent_unified"
_TEMP_DB = _UNIFIED_ROOT / ".temp-db"
_SAMPLES_SRC = _UNIFIED_ROOT.parents[2] / "src"
_HEG_MCP = Path(
    os.environ.get(
        "HEG_FLIGHT_MCP_SERVER",
        str(_UNIFIED_ROOT.parents[5].parent / "heg_flight_mock" / "mcp" / "server.py"),
    )
)

sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT_DIR), str(_ROLES)]

os.environ.setdefault("UNIFIED_MERCHANT", "flight")
os.environ.setdefault("TEMP_DB_DIR", str(_TEMP_DB))
os.environ.setdefault("FLOW", "card")
os.environ.setdefault("HEG_FLIGHT_BACKEND_URL", "http://127.0.0.1:9000")
os.environ.setdefault("AP2_TOKEN_STORE_PATH", str(_TEMP_DB / "ap2_token_store.json"))
os.environ.setdefault(
    "MERCHANT_PAYMENT_PROCESSOR_URL", "http://127.0.0.1:8093/initiate-payment"
)


class _State(dict):
  pass


class _ToolContext:
  def __init__(self) -> None:
    self.state = _State(
        {
            "ap2:payment_method": "card",
            "ap2:presence_mode": "hp",
        }
    )


def _load_heg_mcp():
  spec = importlib.util.spec_from_file_location("heg_flight_mcp", _HEG_MCP)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load HEG MCP from {_HEG_MCP}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def _step(name: str, result: dict) -> dict:
  if isinstance(result, dict) and result.get("error"):
    raise SystemExit(f"FAIL {name}: {result}")
  print(f"OK  {name}")
  return result


async def main() -> None:
  import httpx

  from shopping_agent import merchant_profile
  from shopping_agent.mandate_tools_hp import (
      assemble_and_sign_immediate_mandates_tool,
      create_hp_open_mandates_tool,
  )
  from shopping_agent.merchant_profile import apply_mandate_overrides, get_merchant_profile

  profile = get_merchant_profile("flight")
  apply_mandate_overrides(profile)

  health = httpx.get(f"{profile.heg_backend_url}/health", timeout=10.0)
  health.raise_for_status()
  print(f"OK  HEG backend healthy ({profile.heg_backend_url})")

  heg = _load_heg_mcp()
  ctx = _ToolContext()
  # Use an explicit future date with seeded availability so the query does not
  # drift into a past month (which the parser would bump to next year, where the
  # HEG mock has no inventory). Override via E2E_FLIGHT_SEARCH if needed.
  search_query = os.environ.get(
      "E2E_FLIGHT_SEARCH", "SIN to PVG economy June 21 2026 1 adult"
  )

  search = _step(
      "search_inventory",
      await heg.search_inventory(search_query, constraint_price_cap=800.0),
  )
  matches = search.get("matches") or []
  if not matches:
    raise SystemExit(f"FAIL search_inventory: no matches — {search}")
  item = matches[0]
  item_id = item["item_id"]
  price = float(item["price"])
  print(f"    item_id={item_id} price={price} {item.get('currency', 'USD')}")

  check = _step(
      "check_product",
      await heg.check_product(item_id, constraint_price_cap=800.0),
  )
  if not check.get("available"):
    raise SystemExit(f"FAIL check_product: not available — {check}")

  cart = _step("assemble_cart", await heg.assemble_cart(item_id, 1))
  cart_id = cart["cart_id"]
  total_minor = int(cart["total"])
  price_cap = price + 50.0

  open_m = _step(
      "create_hp_open_mandates",
      create_hp_open_mandates_tool(
          json.dumps(
              {
                  "item_id": item_id,
                  "price_cap": price_cap,
                  "qty": 1,
                  "payment_method": "card",
              }
          ),
          ctx,
      ),
  )
  open_checkout_id = open_m["open_checkout_mandate_id"]

  checkout = _step(
      "create_checkout",
      await heg.create_checkout(cart_id, open_checkout_id),
  )
  checkout_jwt = checkout["checkout_jwt"]
  checkout_jwt_hash = checkout["checkout_jwt_hash"]

  # Trusted Surface approval (HP): mirror the H5 "what you see is what you sign"
  # portal so the assemble gate (check_assemble_allowed) permits signing.
  from trusted_surface_gate import (
      confirm_trusted_surface_approval,
      create_ts_session,
      set_request_session_id,
  )

  ts_session_id = f"e2e-flight-hp-{uuid.uuid4()}"
  ts = _step(
      "create_trusted_surface_session",
      create_ts_session(
          ts_session_id,
          price_cap=price_cap,
          payment_method="card",
          item_id=item_id,
          item_name=str(item.get("name", item_id)),
          presence_mode="hp",
          amount_cents=total_minor,
      ),
  )
  _step(
      "confirm_trusted_surface_approval",
      confirm_trusted_surface_approval(
          ts["ref"], pin=os.environ.get("TS_PIN") or None
      ),
  )
  set_request_session_id(ts_session_id)

  immediate = _step(
      "assemble_and_sign_immediate_mandates",
      assemble_and_sign_immediate_mandates_tool(
          json.dumps(
              {
                  "checkout_jwt": checkout_jwt,
                  "checkout_jwt_hash": checkout_jwt_hash,
                  "amount_cents": total_minor,
                  "item_id": item_id,
                  "price_cap": price_cap,
                  "qty": 1,
                  "payment_method": "card",
                  "payee": profile.merchant.model_dump(exclude_none=True),
              }
          ),
          ctx,
      ),
  )

  from credentials_provider_unified import server as cp_server

  cred = _step(
      "issue_payment_credential",
      cp_server.issue_payment_credential(
          payment_method="card",
          payment_mandate_chain_id=immediate["payment_mandate_chain_id"],
          open_checkout_hash=open_m["open_checkout_hash"],
          checkout_jwt_hash=checkout_jwt_hash,
          payment_nonce=immediate["payment_nonce"],
          presence_mode="hp",
      ),
  )
  payment_token = cred["payment_token"]

  done = _step(
      "complete_checkout",
      await heg.complete_checkout(
          payment_token=payment_token,
          checkout_mandate_id=immediate["checkout_mandate_chain_id"],
          checkout_nonce=immediate["checkout_nonce"],
      ),
  )
  order_id = done.get("order_id")
  print(f"    ap2_order_id={order_id}")

  cart_store_path = _TEMP_DB / "heg_cart_state.json"
  heg_order_id = None
  if cart_store_path.exists():
    cart_store = json.loads(cart_store_path.read_text())
    heg_order_id = (cart_store.get(cart_id) or {}).get("heg_order_id")
  print(f"    heg_order_id={heg_order_id}")

  if heg_order_id:
    resp = httpx.post(
        f"{profile.heg_backend_url}/api/order/queryOrderByOrderId.do",
        json={"orderId": heg_order_id},
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if str(body.get("status")) != "200":
      raise SystemExit(f"FAIL HEG order query: {body}")
    details = body.get("orderDetails") or {}
    status = details.get("status")
    print(f"OK  HEG order query status={status} orderId={heg_order_id}")
    if status != 4:
      raise SystemExit(f"FAIL expected HEG order status=4 (paid), got {status}")
  else:
    print("WARN heg_order_id not found in cart store — skipping HEG order query")

  print("")
  print("E2E flight HP+card PASSED")
  print(f"  flight: {item.get('name', item_id)}")
  print(f"  total: {total_minor / 100:.2f} {cart.get('currency', 'USD')}")
  print(f"  checkout_receipt: {'yes' if done.get('checkout_receipt') else 'no'}")


if __name__ == "__main__":
  asyncio.run(main())
