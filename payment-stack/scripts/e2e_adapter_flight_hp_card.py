#!/usr/bin/env python3
"""E2E: Flight HP + card via ap2-merchant-adapter MCP (QClaw / OpenClaw path).

Mirrors heg-flight skill tool chain:
  search_inventory → check_product → assemble_cart → create_hp_open_mandates
  → create_checkout → assemble_and_sign_immediate_mandates → issue_payment_credential
  → complete_checkout

Requires adapter REST (:8200), HEG (:9000), CP trigger (:8092).

Usage:
  cd payment-stack
  NO_PROXY=127.0.0.1,localhost python scripts/e2e_adapter_flight_hp_card.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

_UNIFIED = Path(__file__).resolve().parents[1]
_AGENT = _UNIFIED / "shopping_agent_unified"
sys.path.insert(0, str(_UNIFIED))
from path_setup import ensure_src_on_path  # noqa: E402

_SAMPLES_SRC = ensure_src_on_path()
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT), str(_UNIFIED)]

os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED / ".temp-db"))
os.environ.setdefault("ADAPTER_BASE_URL", "http://127.0.0.1:8200")
os.environ.setdefault("HEG_FLIGHT_BACKEND_URL", "http://127.0.0.1:9000")
os.environ.setdefault("FLOW", "card")
os.environ.setdefault(
    "HEG_FLIGHT_MCP_SERVER",
    os.environ.get(
        "HEG_FLIGHT_MCP_SERVER",
        "/Users/ouyang/AI-coding/payment/heg_flight_mock/mcp/server.py",
    ),
)

_ADAPTER_MCP = _UNIFIED.parent / "adapter" / "mcp" / "server.py"


def _load_adapter_mcp():
  spec = importlib.util.spec_from_file_location("adapter_mcp", _ADAPTER_MCP)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load adapter MCP from {_ADAPTER_MCP}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


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


def _step(name: str, result: dict) -> dict:
  if isinstance(result, dict) and result.get("error"):
    raise SystemExit(f"FAIL {name}: {result}")
  print(f"OK  {name}")
  return result


async def main() -> None:
  import httpx

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

  profile = get_merchant_profile("flight")
  apply_mandate_overrides(profile)

  health = httpx.get(
      f"{profile.heg_backend_url}/health",
      timeout=10.0,
      trust_env=False,
  )
  health.raise_for_status()
  adapter = httpx.get(
      os.environ["ADAPTER_BASE_URL"] + "/health",
      timeout=10.0,
      trust_env=False,
  )
  adapter.raise_for_status()
  print("OK  HEG + adapter healthy")

  mcp = _load_adapter_mcp()
  ctx = _ToolContext()
  search_query = os.environ.get(
      "E2E_FLIGHT_SEARCH", "SIN to PVG economy June 21 2026 1 adult"
  )

  search = _step(
      "search_inventory",
      await mcp.search_inventory(search_query, constraint_price_cap=800.0),
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
      await mcp.check_product(item_id, constraint_price_cap=800.0),
  )
  if not check.get("available"):
    raise SystemExit(f"FAIL check_product: not available — {check}")

  cart = _step("assemble_cart", await mcp.assemble_cart(item_id, 1))
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

  checkout = _step(
      "create_checkout",
      await mcp.create_checkout(
          cart_id,
          open_m["open_checkout_mandate_id"],
          payment_method="card",
      ),
  )
  checkout_jwt = checkout["checkout_jwt"]
  checkout_jwt_hash = checkout["checkout_jwt_hash"]

  ts_session_id = f"e2e-adapter-flight-hp-{uuid.uuid4()}"
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

  done = _step(
      "complete_checkout",
      await mcp.complete_checkout(
          payment_token=cred["payment_token"],
          checkout_mandate_id=immediate["checkout_mandate_chain_id"],
          checkout_nonce=immediate["checkout_nonce"],
          payment_method="card",
      ),
  )
  order_id = done.get("order_id")
  print(f"    ap2_order_id={order_id}")
  print("")
  print("E2E adapter flight HP+card PASSED (QClaw path)")


if __name__ == "__main__":
  asyncio.run(main())
