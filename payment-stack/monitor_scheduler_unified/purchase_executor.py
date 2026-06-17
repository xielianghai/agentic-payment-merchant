"""Deterministic HNP purchase execution (no LLM)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

_ROLES_DIR = Path(__file__).resolve().parents[1]
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))

from buyer_mcp_unified.session_store import ToolContext, load_tool_context, save_tool_context
from shopping_agent.mandate_bridge import (  # noqa: E402
  create_checkout_presentation,
  create_payment_presentation,
  check_constraints_against_mandate,
  verify_checkout_receipt,
)
from trusted_surface_gate import _canonical_session_id  # noqa: E402

from path_setup import resolve_heg_mcp_server  # noqa: E402


class _BridgeToolContext:
  """Minimal ADK-compatible context for mandate_bridge tools."""

  def __init__(self, state: dict[str, Any]):
    self.state = state


def _heg_mcp_path() -> Path:
  return resolve_heg_mcp_server()


def _load_module(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {path}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def _merchant_backend(merchant: str):
  key = (merchant or "shoe").strip().lower()
  if key in {"flight", "heg", "sq"}:
    return _load_module("heg_flight_mcp", _heg_mcp_path())
  return _load_module(
      "shoe_merchant_mcp", _ROLES_DIR / "merchant_unified" / "server.py"
  )


async def _call_merchant(fn, *args, **kwargs) -> dict[str, Any]:
  result = fn(*args, **kwargs)
  if asyncio.iscoroutine(result):
    result = await result
  if not isinstance(result, dict):
    return {"error": "invalid_merchant_response", "message": str(result)}
  return result


def _tool_context(session_id: str) -> _BridgeToolContext:
  sid = _canonical_session_id(session_id)
  ctx = load_tool_context(sid)
  return _BridgeToolContext(dict(ctx.state))


def _sync_flow(pm: str) -> None:
  os.environ["FLOW"] = pm


def _apply_merchant_mandate_overrides(merchant: str) -> None:
  """Match shopping-agent payee/currency when verifying open mandates."""
  from shopping_agent.merchant_profile import apply_mandate_overrides, get_merchant_profile

  apply_mandate_overrides(get_merchant_profile(merchant))


def execute_hnp_purchase(session_id: str, monitor: dict[str, Any]) -> dict[str, Any]:
  """Run full HNP purchase chain for an armed monitor session."""
  sid = _canonical_session_id(session_id)
  merchant = str(monitor.get("merchant") or "shoe")
  _apply_merchant_mandate_overrides(merchant)
  ctx = load_tool_context(sid)
  pm = str(ctx.state.get("ap2:payment_method", "card")).strip().lower()
  if pm not in ("card", "x402"):
    pm = "card"
  _sync_flow(pm)

  open_checkout_id = str(ctx.state.get("app:open_checkout_mandate_id", "")).strip()
  open_payment_id = str(ctx.state.get("app:open_payment_mandate_id", "")).strip()
  open_checkout_hash = str(ctx.state.get("app:open_checkout_hash", "")).strip()
  if not open_checkout_id or not open_payment_id:
    return {
        "error": "missing_open_mandates",
        "message": (
            "Session is missing app:open_checkout_mandate_id / "
            "app:open_payment_mandate_id. Register monitor with session_state."
        ),
    }

  item_id = str(monitor.get("item_id", "")).strip()
  merchant = str(monitor.get("merchant") or "shoe")
  backend = _merchant_backend(merchant)
  bridge_ctx = _BridgeToolContext(dict(ctx.state))

  async def _run() -> dict[str, Any]:
    cart = await _call_merchant(backend.assemble_cart, item_id, 1)
    if cart.get("error"):
      return cart

    checkout = await _call_merchant(
        backend.create_checkout,
        cart["cart_id"],
        open_checkout_id,
        payment_method=pm,
    )
    if checkout.get("error"):
      return checkout

    total_cents = int(cart.get("total") or 0)
    if total_cents <= 0:
      return {"error": "invalid_total", "message": "Cart total must be positive."}

    payment_nonce = secrets.token_urlsafe(16)
    pay_pres = create_payment_presentation(
        checkout_hash=str(checkout.get("checkout_jwt_hash", "")),
        amount_cents=total_cents,
        nonce=payment_nonce,
        currency=str(cart.get("currency") or monitor.get("currency") or "USD"),
        tool_context=bridge_ctx,
    )
    if pay_pres.get("error"):
      return pay_pres

    payment_mandate_chain_id = str(
        pay_pres.get("payment_mandate_chain_id")
        or pay_pres.get("payment_mandate")
        or ""
    )
    if not payment_mandate_chain_id:
      return {
          "error": "payment_presentation_failed",
          "message": "Missing payment_mandate_chain_id.",
      }

    from credentials_provider_unified import server as cp_server

    cred = cp_server.issue_payment_credential(
        payment_method=pm,
        payment_mandate_chain_id=payment_mandate_chain_id,
        open_checkout_hash=open_checkout_hash or str(checkout.get("open_checkout_hash", "")),
        checkout_jwt_hash=str(checkout.get("checkout_jwt_hash", "")),
        payment_nonce=payment_nonce,
        presence_mode="hnp",
    )
    if isinstance(cred, dict) and cred.get("error"):
      return dict(cred)

    checkout_nonce = secrets.token_urlsafe(16)
    chk_pres = create_checkout_presentation(
        checkout_jwt=str(checkout.get("checkout_jwt", "")),
        checkout_hash=str(checkout.get("checkout_jwt_hash", "")),
        nonce=checkout_nonce,
        tool_context=bridge_ctx,
    )
    if chk_pres.get("error"):
      return chk_pres

    checkout_mandate_chain_id = str(chk_pres.get("checkout_mandate_chain_id", ""))
    if not checkout_mandate_chain_id:
      return {
          "error": "checkout_presentation_failed",
          "message": "Missing checkout_mandate_chain_id.",
      }

    done = await _call_merchant(
        backend.complete_checkout,
        str(cred.get("payment_token", "")),
        checkout_mandate_chain_id,
        checkout_nonce,
        payment_method=pm,
    )
    if done.get("error"):
      return done

    receipt = str(done.get("checkout_receipt") or "")
    if receipt:
      verified = verify_checkout_receipt(receipt)
      if isinstance(verified, dict) and verified.get("error"):
        return verified

    save_tool_context(sid, ToolContext(dict(bridge_ctx.state)))

    purchase_complete = {
        "type": "purchase_complete",
        "order_id": done.get("order_id"),
        "receipt": done.get("checkout_receipt"),
        "payment_method": pm,
        "item_id": item_id,
        "display_name": monitor.get("display_name") or monitor.get("item_name"),
        "total_cents": total_cents,
        "currency": cart.get("currency") or monitor.get("currency") or "USD",
        # Web client Mandates tab fetches full chains by id (same as HP tool intercept).
        "checkout_mandate_chain_id": checkout_mandate_chain_id,
        "payment_mandate_chain_id": payment_mandate_chain_id,
    }
    return {
        "status": "ok",
        "session_id": sid,
        "order_id": done.get("order_id"),
        "payment_method": pm,
        "purchase_complete": purchase_complete,
        "message": "HNP purchase completed by backend scheduler.",
    }

  try:
    return asyncio.run(_run())
  except Exception as exc:
    return {"error": "purchase_exception", "message": str(exc)}


def evaluate_constraints(
    session_id: str,
    *,
    price: float,
    currency: str,
    available: bool,
    merchant: str = "shoe",
) -> dict[str, Any]:
  _apply_merchant_mandate_overrides(merchant)
  bridge_ctx = _tool_context(session_id)
  pm = str(bridge_ctx.state.get("ap2:payment_method", "card"))
  _sync_flow(pm)
  return check_constraints_against_mandate(
      price=price,
      currency=currency,
      available=available,
      tool_context=bridge_ctx,
  )


async def check_product_for_monitor(
    monitor: dict[str, Any],
) -> dict[str, Any]:
  backend = _merchant_backend(str(monitor.get("merchant") or "shoe"))
  item_id = str(monitor.get("item_id", ""))
  price_cap = monitor.get("price_cap")
  return await _call_merchant(
      backend.check_product,
      item_id,
      constraint_price_cap=price_cap,
  )
