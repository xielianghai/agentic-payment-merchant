"""Adapter MCP server — routes merchant tools via UCP REST + HEG AP2 checkout."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

_ADAPTER_ROOT = Path(__file__).resolve().parents[1]
_AP2_SDK_ROOT = Path(os.environ.get("AP2_ROOT", "")).expanduser()
if not _AP2_SDK_ROOT.is_dir():
    _AP2_SDK_ROOT = _ADAPTER_ROOT.parent.parent / "AP2"
_AP2_SDK_ROOT = _AP2_SDK_ROOT / "code" / "sdk" / "python"
for _p in (_ADAPTER_ROOT, _AP2_SDK_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config import get_settings  # noqa: E402
from services.registry import fetch_active_merchants, load_active_merchant_selection  # noqa: E402

mcp = FastMCP("Agentic Payment Merchant Adapter")

_LOG_DIR = Path(os.environ.get("LOGS_DIR", _ADAPTER_ROOT.parent / "payment-stack" / ".logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("adapter-mcp")
_logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(_LOG_DIR / "adapter-mcp.log", mode="a", encoding="utf-8")
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

_HEG_BACKEND: Any = None


def _settings() -> Any:
    settings = get_settings()
    settings.temp_db_dir = os.environ.get("TEMP_DB_DIR", settings.temp_db_dir)
    return settings


def _adapter_base() -> str:
    return os.environ.get("ADAPTER_BASE_URL", _settings().adapter_base_url).rstrip("/")


async def _ucp_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_adapter_base()}{path}"
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def _ucp_get(path: str) -> dict[str, Any]:
    url = f"{_adapter_base()}{path}"
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


def _issue_id_from_checkout_mandate(checkout_mandate_id: str) -> str | None:
    """Extract presale issueId (AP2 cart_id) from closed checkout mandate file."""
    temp_db = Path(os.environ.get("TEMP_DB_DIR", _settings().temp_db_dir))
    path = temp_db / f"{checkout_mandate_id}.sdjwt"
    if not path.is_file():
        return None
    try:
        from ap2.sdk.utils import b64url_decode

        text = path.read_text(encoding="utf-8")
        match = re.search(r'"checkout_jwt"\s*:\s*"(eyJ[^"]+)"', text)
        if not match:
            return None
        jwt = match.group(1)
        payload_b64 = jwt.split(".")[1]
        payload = json.loads(b64url_decode(payload_b64))
        cart_id = payload.get("id")
        return str(cart_id) if cart_id else None
    except Exception as exc:
        _logger.warning("Could not parse issue_id from mandate %s: %s", checkout_mandate_id, exc)
        return None


def _load_heg_mcp() -> Any:
    global _HEG_BACKEND
    if _HEG_BACKEND is not None:
        return _HEG_BACKEND
    heg_path = Path(os.environ.get("HEG_FLIGHT_MCP_SERVER", _settings().heg_mcp_server_path))
    spec = importlib.util.spec_from_file_location("heg_flight_mcp", heg_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load HEG MCP at {heg_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _HEG_BACKEND = mod
    return mod


async def _call_heg(fn_name: str, *args, **kwargs) -> Any:
    fn: Callable[..., Any] = getattr(_load_heg_mcp(), fn_name)
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result


async def get_active_merchant_key() -> str:
    temp_db = os.environ.get("TEMP_DB_DIR", _settings().temp_db_dir)
    selected = load_active_merchant_selection(temp_db)
    if selected:
        return selected
    merchants = await fetch_active_merchants()
    if merchants:
        return str(merchants[0].get("merchant_id") or "heg_flight")
    return "heg_flight"


@mcp.tool()
async def search_inventory(
    product_description: str,
    constraint_price_cap: float | None = None,
) -> dict[str, Any]:
    """Search flights via UCP catalog/search (translated to HEG backend)."""
    merchant = await get_active_merchant_key()
    _logger.info("search_inventory merchant=%s query=%s", merchant, product_description)
    result = await _ucp_post(
        "/catalog/search",
        {"query": product_description, "price_cap": constraint_price_cap},
    )
    matches = []
    for item in result.get("matches") or []:
        display = item.get("name") or item.get("item_id")
        matches.append(
            {
                **item,
                "display_name": display,
                "product_label": display,
            }
        )
    return {
        "matches": matches,
        "message": f"Found {len(matches)} flight(s) via UCP for merchant {merchant}.",
        "protocol": "UCP",
    }


@mcp.tool()
async def check_product(
    item_id: str,
    constraint_price_cap: float | None = None,
) -> dict[str, Any]:
    """Check flight availability via UCP-backed catalog."""
    result = await search_inventory(item_id, constraint_price_cap)
    matches = result.get("matches") or []
    match = next((m for m in matches if m.get("item_id") == item_id), matches[0] if matches else None)
    if not match:
        return {"item_id": item_id, "available": False}
    return {
        "item_id": item_id,
        "price": match.get("price"),
        "available": True,
        "currency": match.get("currency") or "USD",
        "payment_method": "card",
        "payment_method_description": "Card payment via AP2",
        "display_name": match.get("display_name") or item_id,
    }


@mcp.tool()
async def assemble_cart(item_id: str, qty: int) -> dict[str, Any]:
    """Create UCP cart (HEG verify + presale) and return AP2-compatible cart_id."""
    cart = await _ucp_post("/carts", {"item_id": item_id, "qty": qty})
    issue_id = cart.get("issue_id")
    return {
        "cart_id": issue_id or cart.get("id"),
        "ucp_cart_id": cart.get("id"),
        "issue_id": issue_id,
        "total": cart.get("total"),
        "currency": cart.get("currency") or "USD",
        "line_items": cart.get("line_items") or [],
        "protocol": "UCP",
    }


@mcp.tool()
async def create_checkout(
    cart_id: str,
    open_checkout_mandate_id: str,
    payment_method: str = "card",
) -> dict[str, Any]:
    """Create UCP checkout session + AP2 Checkout JWT (ap2_mandate extension)."""
    ucp_checkout = await _ucp_post("/checkout-sessions", {"cart_id": cart_id})
    checkout_id = ucp_checkout.get("id")

    ap2_result = await _call_heg(
        "create_checkout",
        cart_id,
        open_checkout_mandate_id,
        payment_method=payment_method,
    )
    if not isinstance(ap2_result, dict):
        return ap2_result

    checkout_jwt = ap2_result.get("checkout_jwt")
    checkout_hash = ap2_result.get("checkout_jwt_hash") or ap2_result.get("checkout_hash")
    if checkout_id and checkout_jwt and checkout_hash and not ap2_result.get("error"):
        ucp_with_mandate = await _ucp_post(
            f"/checkout-sessions/{checkout_id}/ap2-mandate",
            {"checkout_jwt": checkout_jwt, "checkout_jwt_hash": checkout_hash},
        )
        ap2_result["ucp_checkout_id"] = checkout_id
        ap2_result["ucp_checkout"] = ucp_with_mandate
        ap2_result["ap2_mandate"] = ucp_with_mandate.get("ap2_mandate")
        ap2_result["protocol"] = "UCP+AP2"
    elif checkout_id:
        ap2_result["ucp_checkout_id"] = checkout_id
        ap2_result["protocol"] = "UCP+AP2"
    return ap2_result


@mcp.tool()
async def complete_checkout(
    payment_token: str,
    checkout_mandate_id: str,
    checkout_nonce: str,
    payment_method: str = "card",
) -> dict[str, Any]:
    """Complete AP2 checkout (mandate + MPP) and sync UCP checkout session."""
    ap2_result = await _call_heg(
        "complete_checkout",
        payment_token,
        checkout_mandate_id,
        checkout_nonce,
        payment_method=payment_method,
    )
    if not isinstance(ap2_result, dict):
        return ap2_result

    if ap2_result.get("status") == "success" or ap2_result.get("order_id"):
        issue_id = _issue_id_from_checkout_mandate(checkout_mandate_id)
        ucp_checkout_id = ap2_result.get("ucp_checkout_id")
        if not ucp_checkout_id and issue_id:
            try:
                ucp_checkout = await _ucp_get(f"/checkout-sessions/by-issue/{issue_id}")
                ucp_checkout_id = ucp_checkout.get("id")
            except httpx.HTTPError:
                ucp_checkout_id = None
        if ucp_checkout_id and ap2_result.get("order_id"):
            try:
                ucp_final = await _ucp_post(
                    f"/checkout-sessions/{ucp_checkout_id}/finalize",
                    {
                        "order_id": ap2_result.get("order_id"),
                        "checkout_receipt": ap2_result.get("checkout_receipt"),
                    },
                )
                ap2_result["ucp_checkout"] = ucp_final
            except httpx.HTTPError as exc:
                _logger.warning("UCP finalize failed: %s", exc)
        ap2_result["protocol"] = "UCP+AP2"
    return ap2_result


if __name__ == "__main__":
    mcp.run()
