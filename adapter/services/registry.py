import json
from typing import Any

import httpx

from config import get_settings


async def fetch_active_merchants() -> list[dict[str, Any]]:
    settings = get_settings()
    url = f"{settings.merchant_mgmt_api.rstrip('/')}/api/v1/registry/merchants"
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


async def get_active_merchant(merchant_id: str | None = None) -> dict[str, Any] | None:
    merchants = await fetch_active_merchants()
    if not merchants:
        return None
    if merchant_id:
        for merchant in merchants:
            if merchant.get("merchant_id") == merchant_id:
                return merchant
    return merchants[0]


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
