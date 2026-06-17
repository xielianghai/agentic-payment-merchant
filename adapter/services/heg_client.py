import re
import uuid
from datetime import date, datetime
from typing import Any

import httpx

from config import get_settings


def _routing_key_from_item_id(item_id: str) -> str:
    id_ = (item_id or "").strip()
    if id_.endswith("_0") and id_.startswith("rt_"):
        return id_[:-2]
    return id_


def _parse_search_query(query: str) -> dict[str, Any]:
    text = (query or "").strip()
    upper = text.upper()
    from_city = "SIN"
    to_city = "PVG"
    from_date = "2026-06-10"
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
        month_match = re.search(r"(20\d{2})[-/年](\d{1,2})", text)
        if month_match:
            from_date = f"{month_match.group(1)}-{int(month_match.group(2)):02d}-10"

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
