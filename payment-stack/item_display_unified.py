"""Human-readable product labels for Feishu / openclaw (shoe slugs + flight routing keys)."""

from __future__ import annotations

import re
from typing import Any

_CABIN_LABELS = {
    "y": "Economy",
    "c": "Business",
    "f": "First",
    "j": "Business",
}


def is_internal_flight_item_id(item_id: str) -> bool:
  return bool(re.match(r"^rt_\d", (item_id or "").strip(), re.I))


def is_readable_flight_slug(item_id: str) -> bool:
  id_ = (item_id or "").strip().lower()
  if is_internal_flight_item_id(id_):
    return False
  return bool(re.match(r"^[a-z]{3}_[a-z]{3}_\d{8}_[a-z]_\d+$", id_))


def format_readable_flight_slug(item_id: str) -> str | None:
  id_ = (item_id or "").strip().lower()
  m = re.match(r"^([a-z]{3})_([a-z]{3})_(\d{8})_([a-z])_\d+$", id_)
  if not m:
    return None
  dep, arr, ymd, cabin = m.group(1), m.group(2), m.group(3), m.group(4)
  date = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
  cabin_label = _CABIN_LABELS.get(cabin, cabin.upper())
  return f"{dep.upper()} → {arr.upper()} · {date} · {cabin_label}"


def slug_to_title(item_id: str) -> str:
  base = (item_id or "").strip()
  if base.endswith("_0"):
    base = base[:-2]
  return base.replace("_", " ").strip().title() or base


def resolve_display_name(
    item_id: str,
    *,
    merchant: str = "shoe",
    item_name: str | None = None,
    product: dict[str, Any] | None = None,
) -> str:
  """Best user-facing label; never return a bare routing key when avoidable."""
  hint = (item_name or "").strip()
  if hint and hint != item_id:
    return hint

  prod = product or {}
  for key in ("display_name", "name", "item_name", "product_label"):
    val = prod.get(key)
    if isinstance(val, str) and val.strip() and val.strip() != item_id:
      return val.strip()

  if (merchant or "").strip().lower() in {"flight", "heg", "sq"}:
    route = prod.get("route_summary")
    if isinstance(route, str) and route.strip():
      return route.strip()
    fn = str(prod.get("flight_no") or "").strip()
    dep = str(prod.get("from_city") or prod.get("departure") or "").strip().upper()
    arr = str(prod.get("to_city") or prod.get("arrival") or "").strip().upper()
    date = str(prod.get("from_date") or prod.get("date") or "").strip()
    cabin = str(prod.get("cabin_class") or prod.get("cabin") or "").strip()
    if fn and dep and arr:
      parts = [f"{fn} {dep}→{arr}"]
      if date:
        parts.append(date)
      if cabin:
        parts.append(_CABIN_LABELS.get(cabin.lower(), cabin))
      return " · ".join(parts)
    from_slug = format_readable_flight_slug(item_id)
    if from_slug:
      return from_slug
    if is_internal_flight_item_id(item_id):
      if fn:
        return f"{fn} flight"
      return "Flight booking"
    return slug_to_title(item_id)

  return slug_to_title(item_id)


def enrich_check_product_response(
    result: dict[str, Any],
    *,
    merchant: str = "shoe",
    item_name: str | None = None,
) -> dict[str, Any]:
  """Add display_name / product_label for Feishu tables (keeps item_id for tools)."""
  if not isinstance(result, dict) or result.get("error"):
    return result
  item_id = str(result.get("item_id", ""))
  display = resolve_display_name(
      item_id,
      merchant=merchant,
      item_name=item_name,
      product=result,
  )
  result["display_name"] = display
  result["product_label"] = display
  if display != item_id:
    result["reference_id"] = item_id
  return result
