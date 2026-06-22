from typing import Any

DEFAULT_VERSION = "2026-01-23"

SCHEMA_URLS: dict[str, str] = {
    "dev.ucp.shopping.catalog.search": "https://ucp.dev/2026-01-23/schemas/shopping/catalog_lookup.json",
    "dev.ucp.shopping.cart": "https://ucp.dev/2026-01-23/schemas/shopping/cart.json",
    "dev.ucp.shopping.checkout": "https://ucp.dev/2026-01-23/schemas/shopping/checkout.json",
    "dev.ucp.shopping.order": "https://ucp.dev/2026-01-23/schemas/shopping/order.json",
    "dev.ucp.shopping.ap2_mandate": "https://ucp.dev/2026-01-23/schemas/shopping/ap2_mandate.json",
}


def resolve_schema_url(capability_id: str, version: str = DEFAULT_VERSION) -> str | None:
    if capability_id in SCHEMA_URLS:
        return SCHEMA_URLS[capability_id]
    if capability_id.startswith("dev.ucp.travel.hotel."):
        suffix = capability_id.removeprefix("dev.ucp.travel.hotel.")
        return f"https://ucp.dev/{version}/schemas/travel/hotel_{suffix}.json"
    return None


def default_line_items_schema(vertical: str | None) -> dict[str, Any]:
    if vertical == "airline":
        return {"type": "flight", "fields": ["route", "cabin", "passenger_count"]}
    if vertical == "hotel":
        return {
            "type": "hotel",
            "fields": ["hotel_id", "room_type", "check_in", "check_out", "guest_count"],
        }
    if vertical == "travel":
        return {
            "type": "travel_package",
            "fields": ["package_id", "destination", "start_date", "end_date", "travelers"],
        }
    return {}


def default_config_json(capability_id: str) -> dict[str, Any]:
    if capability_id == "dev.ucp.shopping.ap2_mandate":
        return {"extends": "dev.ucp.shopping.checkout"}
    return {}


def enrich_capability_payload(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    version = enriched.get("version") or DEFAULT_VERSION
    enriched["version"] = version

    capability_id = enriched.get("capability_id") or ""
    if not enriched.get("schema_url"):
        resolved = resolve_schema_url(capability_id, version)
        if resolved:
            enriched["schema_url"] = resolved

    if not enriched.get("line_items_schema"):
        enriched["line_items_schema"] = default_line_items_schema(enriched.get("vertical"))

    if not enriched.get("config_json"):
        enriched["config_json"] = default_config_json(capability_id)

    return enriched
