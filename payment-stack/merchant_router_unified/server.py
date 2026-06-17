"""Unified merchant MCP router — delegates to SuperShoe or HEG flight by session."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

_ROLES_DIR = Path(__file__).resolve().parents[1]
if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))

_UNIFIED_SCENARIO = _ROLES_DIR.parent


def _selection_file() -> Path:
  temp_db = Path(os.environ.get("TEMP_DB_DIR", _UNIFIED_SCENARIO / ".temp-db"))
  return temp_db / "unified_merchant.json"


def _normalize_merchant_key(key: str) -> str:
  normalized = key.strip().lower()
  if normalized in {"flight", "heg", "sq", "singapore_airlines"}:
    return "flight"
  return "shoe"


def get_active_merchant_key() -> str:
  """Active merchant from the session selection file, then env default.

  Self-contained on purpose: importing shopping_agent.* here would drag in the
  ADK/litellm stack and slow MCP startup past the session handshake timeout.
  """
  import json

  try:
    path = _selection_file()
    if path.is_file():
      data = json.loads(path.read_text(encoding="utf-8"))
      if isinstance(data, dict) and data.get("merchant"):
        return _normalize_merchant_key(str(data["merchant"]))
  except (OSError, ValueError, TypeError):
    pass
  return _normalize_merchant_key(os.environ.get("UNIFIED_MERCHANT", "shoe"))


mcp = FastMCP("Unified Merchant Router")

_LOG_DIR = Path(os.environ.get("LOGS_DIR", _ROLES_DIR.parent / ".logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("merchant-router")
_logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(_LOG_DIR / "merchant-router.log", mode="a", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
_logger.addHandler(_handler)

mcp.add_middleware(
    LoggingMiddleware(
        logger=_logger,
        include_payloads=True,
        include_payload_length=True,
        max_payload_length=4000,
    )
)


def _load_module(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {path}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


from path_setup import resolve_heg_mcp_server  # noqa: E402


def _heg_mcp_path() -> Path:
  return resolve_heg_mcp_server()


# Lazy, cached backend loaders. Loading happens on first tool call (within the
# tool-call timeout) rather than at startup, keeping the MCP session handshake
# fast and isolating a bad flight path so it can't break shoe routing.
_BACKENDS: dict[str, Any] = {}


def _backend():
  key = get_active_merchant_key()
  _logger.info("routing merchant=%s", key)
  if key not in _BACKENDS:
    if key == "flight":
      _BACKENDS[key] = _load_module("heg_flight_mcp", _heg_mcp_path())
    else:
      _BACKENDS[key] = _load_module(
          "shoe_merchant_mcp", _ROLES_DIR / "merchant_unified" / "server.py"
      )
  return _BACKENDS[key]


async def _call(fn_name: str, *args, **kwargs) -> Any:
  fn: Callable[..., Any] = getattr(_backend(), fn_name)
  result = fn(*args, **kwargs)
  if asyncio.iscoroutine(result):
    return await result
  return result


@mcp.tool()
async def search_inventory(
    product_description: str,
    constraint_price_cap: float | None = None,
) -> dict[str, Any]:
  """Search inventory (SuperShoe) or flights (Singapore Airlines) for the active merchant."""
  from item_display_unified import resolve_display_name

  result = await _call(
      "search_inventory", product_description, constraint_price_cap
  )
  if not isinstance(result, dict):
    return result
  merchant = get_active_merchant_key()
  matches = result.get("matches")
  if isinstance(matches, list):
    for match in matches:
      if not isinstance(match, dict):
        continue
      item_id = str(match.get("item_id", ""))
      display = resolve_display_name(
          item_id,
          merchant=merchant,
          item_name=str(match.get("name") or ""),
          product=match,
      )
      match["display_name"] = display
      match["product_label"] = display
  return result


@mcp.tool()
async def check_product(
    item_id: str,
    constraint_price_cap: float | None = None,
) -> dict[str, Any]:
  """Check product or flight availability for the active merchant."""
  from item_display_unified import enrich_check_product_response

  result = await _call("check_product", item_id, constraint_price_cap)
  if isinstance(result, dict):
    return enrich_check_product_response(
        result, merchant=get_active_merchant_key()
    )
  return result


@mcp.tool()
async def assemble_cart(item_id: str, qty: int) -> dict[str, Any]:
  """Assemble cart or lock flight seats for the active merchant."""
  return await _call("assemble_cart", item_id, qty)


@mcp.tool()
async def create_checkout(
    cart_id: str,
    open_checkout_mandate_id: str,
    payment_method: str = "card",
) -> dict[str, Any]:
  """Create AP2 checkout for the active merchant."""
  return await _call(
      "create_checkout",
      cart_id,
      open_checkout_mandate_id,
      payment_method=payment_method,
  )


@mcp.tool()
async def complete_checkout(
    payment_token: str,
    checkout_mandate_id: str,
    checkout_nonce: str,
    payment_method: str = "card",
) -> dict[str, Any]:
  """Complete checkout and payment for the active merchant."""
  return await _call(
      "complete_checkout",
      payment_token,
      checkout_mandate_id,
      checkout_nonce,
      payment_method=payment_method,
  )


if __name__ == "__main__":
  mcp.run()
