import re
import uuid
from datetime import date, datetime
from typing import Any

import httpx

from config import get_settings

_MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _routing_key_from_item_id(item_id: str) -> str:
    id_ = (item_id or "").strip()
    if id_.endswith("_0") and id_.startswith("rt_"):
        return id_[:-2]
    return id_


def _parse_search_query(query: str) -> dict[str, Any]:
    text = (query or "").strip()
    upper = text.upper()
    lower = text.lower()
    from_city = "SIN"
    to_city = "PVG"
    from_date = "2026-07-21"
    cabin = "Y"
    adult_num = 1

    codes = re.findall(r"\b([A-Z]{3})\b", upper)
    if len(codes) >= 2:
        from_city, to_city = codes[0], codes[1]
    elif "PVG" in upper or "上海" in text:
        to_city = "PVG"
    elif "BKK" in upper or "曼谷" in text:
        to_city = "BKK"

    date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if date_match:
        from_date = date_match.group(1)
    else:
        ymd_match = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", text)
        if ymd_match:
            from_date = f"{ymd_match.group(1)}-{ymd_match.group(2)}-{ymd_match.group(3)}"
        else:
            for month_name, month_num in _MONTH_NAMES.items():
                month_match = re.search(
                    rf"\b{month_name}\s+(\d{{1,2}})(?:\s+(20\d{{2}}))?\b",
                    lower,
                )
                if not month_match:
                    continue
                day = int(month_match.group(1))
                year = int(month_match.group(2)) if month_match.group(2) else date.today().year
                try:
                    travel = date(year, month_num, day)
                    if not month_match.group(2) and travel < date.today():
                        travel = date(year + 1, month_num, day)
                    from_date = travel.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

    if "BUSINESS" in upper or "商务" in text or " C " in f" {upper} ":
        cabin = "C"
    elif "FIRST" in upper or "头等" in text:
        cabin = "F"

    adult_match = re.search(r"(\d+)\s*(adult|成人|位)", text, re.I)
    if adult_match:
        adult_num = max(1, int(adult_match.group(1)))

    return {
        "fromCity": from_city,
        "toCity": to_city,
        "fromDate": from_date,
        "cabinClass": cabin,
        "adultNum": adult_num,
        "childNum": 0,
        "infantNum": 0,
        "tripType": "1",
    }


class HegClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.heg_flight_backend_url).rstrip("/")

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    async def search_flights(self, query: str, price_cap: float | None = None) -> list[dict[str, Any]]:
        body = _parse_search_query(query)
        result = await self._post("/api/flight/searchFlight.do", body)
        matches: list[dict[str, Any]] = []
        for routing in result.get("routings") or []:
            price_info = routing.get("priceInfo") or {}
            total = float(price_info.get("totalPrices") or 0)
            if price_cap is not None and total > price_cap:
                continue
            data_key = str(routing.get("data") or "")
            item_id = data_key.replace("-", "_").lower() + "_0"
            segments = routing.get("fromSegments") or [{}]
            seg = segments[0] if segments else {}
            name = (
                f"{seg.get('flightNo', 'SQ')} {seg.get('depCity', body['fromCity'])}→"
                f"{seg.get('arrCity', body['toCity'])} · {body['fromDate']} · Economy"
            )
            matches.append(
                {
                    "item_id": item_id,
                    "routing_key": data_key,
                    "name": name,
                    "price": total,
                    "currency": price_info.get("currency") or "USD",
                    "stock": 1,
                    "available": True,
                    "search_body": body,
                }
            )
        return matches

    async def verify_price(self, routing_key: str, search_body: dict[str, Any]) -> dict[str, Any]:
        payload = {"data": routing_key, **search_body}
        return await self._post("/api/verify/verifyPrice.do", payload)

    async def issue_presale(self, session_id: str, routing_key: str, search_body: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "sessionId": session_id,
            "data": routing_key,
            "adultNum": search_body.get("adultNum", 1),
            "childNum": 0,
            "infantNum": 0,
            "holdHours": 24,
            "passengers": [
                {
                    "passengerNo": 1,
                    "passengerType": 1,
                    "gender": 1,
                    "firstName": "MOCK",
                    "lastName": "PASSENGER",
                    "dateOfBirth": "1990-01-01",
                }
            ],
        }
        return await self._post("/api/presale/issue.do", payload)

    async def confirm_presale(self, issue_id: str) -> dict[str, Any]:
        return await self._post("/api/presale/confirm.do", {"issueId": issue_id})

    async def pay_order(self, order_id: str) -> dict[str, Any]:
        return await self._post("/api/order/pay.do", {"orderId": order_id})
