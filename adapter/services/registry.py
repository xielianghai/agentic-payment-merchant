import json
import os
import time
from typing import Any

import httpx

from config import get_settings

DEFAULT_REGISTRY_MERCHANT_ID = "heg_flight"
_CATALOG_CAPABILITY_KEYS = frozenset(
    {
        "catalog",
        "dev.ucp.shopping.catalog.search",
    }
)

_registry_cache: dict[str, Any] = {"expires_at": 0.0, "merchants": []}
_REGISTRY_CACHE_TTL_SECONDS = 5.0


class MerchantUnavailableError(Exception):
    def __init__(self, merchant_id: str, message: str | None = None) -> None:
        self.merchant_id = merchant_id
        self.message = message or (
            "No matching merchant products were found. "
            "Please try another merchant or product."
        )
        super().__init__(self.message)

    def as_dict(self) -> dict[str, str]:
        return {
            "error": "merchant_unavailable",
            "merchant_id": self.merchant_id,
            "message": self.message,
        }


def normalize_registry_merchant_id(merchant_id: str | None = None) -> str:
    normalized = (merchant_id or "").strip().lower()
    if normalized in {"", "flight", "heg", "sq", "singapore_airlines"}:
        return DEFAULT_REGISTRY_MERCHANT_ID
    return merchant_id or DEFAULT_REGISTRY_MERCHANT_ID


def merchant_unavailable_dict(merchant_id: str, message: str | None = None) -> dict[str, str]:
    return MerchantUnavailableError(merchant_id, message).as_dict()


async def fetch_active_merchants(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    if (
        not force_refresh
        and _registry_cache["merchants"]
        and now < float(_registry_cache["expires_at"])
    ):
        return list(_registry_cache["merchants"])

    settings = get_settings()
    url = f"{settings.merchant_mgmt_api.rstrip('/')}/api/v1/registry/merchants"
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data") or []
    merchants = data if isinstance(data, list) else []
    _registry_cache["merchants"] = merchants
    _registry_cache["expires_at"] = now + _REGISTRY_CACHE_TTL_SECONDS
    return merchants


async def get_active_merchant(merchant_id: str | None = None) -> dict[str, Any] | None:
    merchants = await fetch_active_merchants()
    if not merchants:
        return None
    target = normalize_registry_merchant_id(merchant_id)
    for merchant in merchants:
        if merchant.get("merchant_id") == target:
            return merchant
    return None


def _merchant_has_catalog_capability(merchant: dict[str, Any]) -> bool:
    capabilities = merchant.get("capabilities") or []
    if not isinstance(capabilities, list):
        return False
    return any(str(cap).strip() in _CATALOG_CAPABILITY_KEYS for cap in capabilities)


async def assert_merchant_active(merchant_id: str | None = None) -> dict[str, Any]:
    target = normalize_registry_merchant_id(merchant_id)
    merchant = await get_active_merchant(target)
    if not merchant:
        raise MerchantUnavailableError(target)
    if not _merchant_has_catalog_capability(merchant):
        raise MerchantUnavailableError(
            target,
            "No matching merchant products were found. "
            "Please try another merchant or product.",
        )
    return merchant


def save_active_merchant_selection(merchant_id: str, temp_db_dir: str) -> None:
    from pathlib import Path

    path = Path(temp_db_dir) / "active_merchant.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"merchant_id": merchant_id}), encoding="utf-8")


def load_active_merchant_selection(temp_db_dir: str) -> str | None:
    from pathlib import Path

    path = Path(temp_db_dir) / "active_merchant.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("merchant_id"):
            return str(data["merchant_id"])
    except (OSError, ValueError, TypeError):
        pass
    return None


async def resolve_active_merchant_id(merchant_id: str | None = None) -> str:
    explicit = normalize_registry_merchant_id(merchant_id) if merchant_id else None
    if explicit:
        await assert_merchant_active(explicit)
        return explicit

    temp_db = os.environ.get("TEMP_DB_DIR", get_settings().temp_db_dir)
    selected = load_active_merchant_selection(temp_db)
    if selected:
        selected = normalize_registry_merchant_id(selected)
        await assert_merchant_active(selected)
        return selected

    merchants = await fetch_active_merchants()
    if not merchants:
        raise MerchantUnavailableError(DEFAULT_REGISTRY_MERCHANT_ID)

    first_id = str(merchants[0].get("merchant_id") or DEFAULT_REGISTRY_MERCHANT_ID)
    await assert_merchant_active(first_id)
    return first_id
