"""Adapter MCP server — routes merchant tools via UCP REST + HEG AP2 checkout."""


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
from services.heg_client import _routing_key_from_item_id  # noqa: E402
from services.registry import (  # noqa: E402
    MerchantUnavailableError,
    resolve_active_merchant_id,
)

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
    import inspect

    from fastmcp.tools import FunctionTool as _FunctionTool

    fn: Callable[..., Any] = getattr(_load_heg_mcp(), fn_name)
    if isinstance(fn, _FunctionTool):
        target = getattr(fn, "fn", None) or getattr(fn, "_fn", None)
        if target is not None and args:
            params = list(inspect.signature(target).parameters.keys())
            for i, value in enumerate(args):
                if i < len(params) and params[i] not in kwargs:
                    kwargs[params[i]] = value
        result = await fn.run(kwargs)
        if hasattr(result, "structured_content") and result.structured_content:
            return result.structured_content
        if hasattr(result, "content"):
            return result.content
        return result
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result


def _heg_flight_state_path() -> Path:
    return Path(os.environ.get("TEMP_DB_DIR", _settings().temp_db_dir)) / "heg_flight_state.json"


def _seed_heg_flight_state(item_id: str, item: dict[str, Any]) -> None:
    """Ensure HEG MCP flight state exists when search went through UCP only."""
    path = _heg_flight_state_path()
    state: dict[str, Any] = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
    search_body = item.get("search_body") or {}
    routing_key = item.get("routing_key") or _routing_key_from_item_id(item_id)
    state[item_id] = {
        "routing_key": routing_key,
        "from_city": search_body.get("fromCity", "SIN"),
        "to_city": search_body.get("toCity", "PVG"),
        "from_date": search_body.get("fromDate", "2026-07-21"),
        "cabin_class": search_body.get("cabinClass", "Y"),
        "adult_num": search_body.get("adultNum", 1),
        "price": item.get("price", 0),
        "currency": item.get("currency", "USD"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def _guard_commerce(merchant_id: str | None = None) -> str:
    try:
        return await resolve_active_merchant_id(merchant_id)
    except MerchantUnavailableError as exc:
        _logger.warning("merchant unavailable: %s", exc.message)
        raise


async def get_active_merchant_key() -> str:
    return await resolve_active_merchant_id()


@mcp.tool()
async def search_inventory(
    product_description: str,
    constraint_price_cap: float | None = None,
) -> dict[str, Any]:
    """Search flights via UCP catalog/search (translated to HEG backend)."""
    try:
        merchant = await _guard_commerce()
    except MerchantUnavailableError as exc:
        return exc.as_dict()
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
    """Check flight availability via verify_price using cached catalog item."""
    try:
        await _guard_commerce()
    except MerchantUnavailableError as exc:
        return exc.as_dict()

    from services.ucp_service import UcpService

    svc = UcpService()
    item = svc.store.get_item(item_id)
    if not item and not (item_id or "").strip().startswith("rt_"):
        # Natural-language fallback only when item_id is not an HEG routing slug.
        result = await search_inventory(item_id, constraint_price_cap)
        matches = result.get("matches") or []
        item = next((m for m in matches if m.get("item_id") == item_id), None)
        if item:
            svc.store.save_item(item_id, item)

    if not item:
        return {
            "item_id": item_id,
            "available": False,
            "message": f"Flight {item_id!r} not found. Call search_inventory first.",
        }

    routing_key = item.get("routing_key") or _routing_key_from_item_id(item_id)
    search_body = item.get("search_body") or {}
    verify = await svc.heg.verify_price(routing_key, search_body)
    if str(verify.get("status")) != "200":
        return {
            "item_id": item_id,
            "price": item.get("price"),
            "available": False,
            "currency": item.get("currency") or "USD",
            "message": verify.get("msg") or "Flight not available or no seats at this time.",
            "display_name": item.get("name") or item_id,
        }

    price_info = (verify.get("routing") or {}).get("priceInfo") or {}
    total = float(price_info.get("totalPrices") or item.get("price") or 0)
    if constraint_price_cap is not None and total > constraint_price_cap:
        return {
            "item_id": item_id,
            "price": total,
            "available": False,
            "currency": price_info.get("currency") or item.get("currency") or "USD",
            "message": f"Price {total} exceeds cap {constraint_price_cap}.",
            "display_name": item.get("name") or item_id,
        }

    return {
        "item_id": item_id,
        "price": total,
        "available": True,
        "currency": price_info.get("currency") or item.get("currency") or "USD",
        "payment_method": "card",
        "payment_method_description": "Card payment via AP2",
        "display_name": item.get("name") or item_id,
    }


@mcp.tool()
async def assemble_cart(item_id: str, qty: int) -> dict[str, Any]:
    """Create UCP cart synced with HEG MCP presale (single issueId for AP2 checkout)."""
    try:
        await _guard_commerce()
    except MerchantUnavailableError as exc:
        return exc.as_dict()

    from services.ucp_service import UcpService

    svc = UcpService()
    item = svc.store.get_item(item_id)
    if not item:
        matches = await svc.catalog_search(item_id)
        catalog_matches = matches.get("matches") or []
        item = next((m for m in catalog_matches if m.get("item_id") == item_id), None)
    if not item:
        return {
            "error": "item_not_found",
            "message": f"Flight {item_id!r} not found. Call search_inventory first.",
        }

    _seed_heg_flight_state(item_id, item)
    heg_cart = await _call_heg("assemble_cart", item_id, qty)
    if isinstance(heg_cart, dict) and heg_cart.get("error"):
        return heg_cart

    ucp_cart = await svc.register_heg_cart(item_id, qty, heg_cart)
    issue_id = ucp_cart.get("issue_id") or heg_cart.get("cart_id")
    return {
        "cart_id": issue_id,
        "ucp_cart_id": ucp_cart.get("id"),
        "issue_id": issue_id,
        "total": heg_cart.get("total"),
        "currency": heg_cart.get("currency") or "USD",
        "line_items": heg_cart.get("line_items") or [],
        "protocol": "UCP+AP2",
        "reused": heg_cart.get("reused", False),
    }


@mcp.tool()
async def create_checkout(
    cart_id: str,
    open_checkout_mandate_id: str,
    payment_method: str = "card",
) -> dict[str, Any]:
    """Create UCP checkout session + AP2 Checkout JWT (ap2_mandate extension)."""
    try:
        await _guard_commerce()
    except MerchantUnavailableError as exc:
        return exc.as_dict()

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


def _purchase_complete_from_checkout(
    ap2_result: dict[str, Any],
    checkout: dict[str, Any] | None,
    payment_method: str,
) -> dict[str, Any] | None:
    order_id = ap2_result.get("order_id")
    if not order_id:
        return None
    line_items = (checkout or {}).get("line_items") or []
    first_item = line_items[0] if line_items else {}
    item_id = first_item.get("item_id") or (checkout or {}).get("item_id")
    item_name = first_item.get("item_name") or item_id
    total_cents = (checkout or {}).get("total") or ap2_result.get("total_cents")
    currency = (checkout or {}).get("currency") or ap2_result.get("currency") or "USD"
    return {
        "type": "purchase_complete",
        "order_id": order_id,
        "item_id": item_id,
        "item_name": item_name,
        "total_cents": total_cents,
        "currency": currency,
        "payment_method": payment_method,
        "payment_method_description": (
            "x402 · MetaMask · SepoliaETH (Sepolia)"
            if payment_method == "x402"
            else "Card •••4242"
        ),
        "status": "success",
        "receipt": {
            "order_id": order_id,
            "checkout_receipt": ap2_result.get("checkout_receipt"),
            "payment_receipt": ap2_result.get("payment_receipt"),
            "ucp_checkout_id": (checkout or {}).get("id"),
            "protocol": "UCP+AP2",
        },
    }


@mcp.tool()
async def complete_checkout(
    payment_token: str,
    checkout_mandate_id: str,
    checkout_nonce: str,
    payment_method: str = "card",
) -> dict[str, Any]:
    """Complete AP2 checkout (mandate + MPP) and sync UCP checkout session."""
    try:
        await _guard_commerce()
    except MerchantUnavailableError as exc:
        return exc.as_dict()

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
        ucp_final = None
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
        checkout_for_receipt = ucp_final
        if checkout_for_receipt is None and ucp_checkout_id:
            try:
                checkout_for_receipt = await _ucp_get(
                    f"/checkout-sessions/{ucp_checkout_id}"
                )
            except httpx.HTTPError:
                checkout_for_receipt = None
        purchase_complete = _purchase_complete_from_checkout(
            ap2_result, checkout_for_receipt, payment_method
        )
        if purchase_complete:
            ap2_result["purchase_complete"] = purchase_complete
            ap2_result["message"] = (
                "Checkout complete. Emit purchase_complete exactly as returned; "
                "do not ask the user for item or cart details."
            )
        ap2_result["protocol"] = "UCP+AP2"
    return ap2_result


if __name__ == "__main__":
    mcp.run()
