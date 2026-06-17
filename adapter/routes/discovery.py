import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from config import get_settings

router = APIRouter(tags=["discovery"])

_PROFILE_TEMPLATE = {
    "version": "2026-01-23",
    "services": {
        "dev.ucp.shopping": [
            {
                "version": "2026-01-23",
                "transport": "rest",
                "endpoint": "{{ENDPOINT}}",
                "schema": "https://ucp.dev/2026-01-23/services/shopping/openapi.json",
            },
            {
                "version": "2026-01-23",
                "transport": "mcp",
                "endpoint": "{{ENDPOINT}}/mcp",
                "schema": "https://ucp.dev/2026-01-23/services/shopping/openrpc.json",
            },
            {
                "version": "2026-01-23",
                "transport": "a2a",
                "endpoint": "{{ENDPOINT}}/.well-known/agent-card.json",
            },
        ]
    },
    "capabilities": {
        "dev.ucp.shopping.catalog.search": [{"version": "2026-01-23", "schema": "https://ucp.dev/2026-01-23/schemas/shopping/catalog_lookup.json"}],
        "dev.ucp.shopping.cart": [{"version": "2026-01-23", "schema": "https://ucp.dev/2026-01-23/schemas/shopping/cart.json"}],
        "dev.ucp.shopping.checkout": [{"version": "2026-01-23", "schema": "https://ucp.dev/2026-01-23/schemas/shopping/checkout.json"}],
        "dev.ucp.shopping.order": [{"version": "2026-01-23", "schema": "https://ucp.dev/2026-01-23/schemas/shopping/order.json"}],
        "dev.ucp.shopping.ap2_mandate": [
            {
                "version": "2026-01-23",
                "schema": "https://ucp.dev/2026-01-23/schemas/shopping/ap2_mandate.json",
                "extends": "dev.ucp.shopping.checkout",
            }
        ],
    },
    "payment_handlers": {
        "dev.mock.payment_handler": [
            {"id": "mock_payment_handler", "name": "mock_payment_handler", "version": "2026-01-23", "config": {}}
        ]
    },
}


@router.get("/.well-known/ucp")
async def ucp_profile(request: Request) -> dict[str, Any]:
    settings = get_settings()
    endpoint = str(request.base_url).rstrip("/")
    profile = json.loads(json.dumps(_PROFILE_TEMPLATE).replace("{{ENDPOINT}}", endpoint))
    profile["signing_keys"] = _load_signing_keys(settings.temp_db_dir)
    return profile


@router.get("/.well-known/agent-card.json")
async def agent_card(request: Request) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    return {
        "name": "AgenticPaymentMerchantAdapter",
        "description": "UCP + AP2 merchant adapter for onboarded merchants",
        "url": f"{base}/a2a/adapter",
        "version": "1.0.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "flight_commerce",
                "name": "Flight Commerce",
                "description": "Search and purchase flights via UCP + AP2",
                "tags": ["ucp", "ap2", "flight"],
            }
        ],
    }


def _load_signing_keys(temp_db_dir: str) -> list[dict[str, Any]]:
    pub_path = Path(temp_db_dir) / "merchant_signing_key.pub"
    if not pub_path.exists():
        return []
    try:
        jwk = json.loads(pub_path.read_text(encoding="utf-8"))
        return [jwk]
    except (OSError, ValueError):
        return []
