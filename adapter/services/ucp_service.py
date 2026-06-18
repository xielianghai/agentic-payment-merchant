from typing import Any

from config import get_settings
from services.heg_client import HegClient, _routing_key_from_item_id
from services.ucp_store import UcpSessionStore


class UcpService:
    def __init__(self) -> None:
        settings = get_settings()
        self.heg = HegClient()
        self.store = UcpSessionStore(settings.temp_db_dir)

    async def catalog_search(self, query: str, price_cap: float | None = None) -> dict[str, Any]:
        matches = await self.heg.search_flights(query, price_cap=price_cap)
        for match in matches:
            self.store.save_item(match["item_id"], match)
        return {
            "results": [
                {
                    "id": m["item_id"],
                    "title": m["name"],
                    "price": {"amount": int(m["price"] * 100), "currency": m["currency"]},
                    "available": m["available"],
                }
                for m in matches
            ],
            "matches": matches,
        }

    async def create_cart(self, item_id: str, qty: int = 1) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            matches = await self.heg.search_flights(item_id)
            item = next((m for m in matches if m["item_id"] == item_id), matches[0] if matches else None)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        routing_key = item.get("routing_key") or _routing_key_from_item_id(item_id)
        search_body = item.get("search_body") or {}
        verify = await self.heg.verify_price(routing_key, search_body)
        if verify.get("status") != "200":
            raise ValueError(verify.get("msg") or "Price verify failed")

        session_id = verify.get("sessionId")
        presale = await self.heg.issue_presale(session_id, routing_key, search_body)
        if presale.get("status") != "200":
            raise ValueError(presale.get("msg") or "Presale issue failed")

        issue_id = presale.get("issueId")
        price_info = presale.get("priceInfo") or item
        total = float(price_info.get("totalPrices") or item.get("price") or 0)
        cart_id = self.store.new_id("CART")
        cart = {
            "id": cart_id,
            "issue_id": issue_id,
            "item_id": item_id,
            "qty": qty,
            "total": int(total * 100),
            "currency": item.get("currency") or "USD",
            "line_items": [
                {
                    "item_id": item_id,
                    "qty": qty,
                    "unit_price": int(total * 100),
                    "item_name": item.get("name"),
                }
            ],
        }
        self.store.save_cart(cart_id, cart)
        return cart

    async def register_heg_cart(
        self,
        item_id: str,
        qty: int,
        heg_cart: dict[str, Any],
    ) -> dict[str, Any]:
        """Mirror an HEG MCP cart (presale issueId) into the UCP store."""
        issue_id = heg_cart.get("cart_id")
        if not issue_id:
            raise ValueError("HEG cart missing cart_id (issueId)")

        item = self.store.get_item(item_id) or {}
        total_minor = int(heg_cart.get("total") or 0)
        line_items = heg_cart.get("line_items") or [
            {
                "item_id": item_id,
                "qty": qty,
                "unit_price": total_minor,
                "item_name": item.get("name"),
            }
        ]
        cart_id = self.store.new_id("CART")
        cart = {
            "id": cart_id,
            "issue_id": issue_id,
            "item_id": item_id,
            "qty": qty,
            "total": total_minor,
            "currency": heg_cart.get("currency") or item.get("currency") or "USD",
            "line_items": line_items,
        }
        self.store.save_cart(cart_id, cart)
        return cart

    async def create_checkout_session(self, cart_ref: str) -> dict[str, Any]:
        cart = self.store.get_cart(cart_ref)
        if not cart:
            raise ValueError(f"Cart not found: {cart_ref}")
        cart_id = cart["id"]
        checkout_id = self.store.new_id("CHK")
        checkout = {
            "id": checkout_id,
            "cart_id": cart_id,
            "issue_id": cart["issue_id"],
            "status": "requires_payment",
            "total": cart["total"],
            "currency": cart["currency"],
            "line_items": cart["line_items"],
            "ap2_mandate": None,
        }
        self.store.save_checkout(checkout_id, checkout)
        return checkout

    async def attach_ap2_checkout(
        self,
        checkout_id: str,
        checkout_jwt: str,
        checkout_jwt_hash: str,
    ) -> dict[str, Any]:
        checkout = self.store.get_checkout(checkout_id)
        if not checkout:
            raise ValueError(f"Checkout not found: {checkout_id}")
        checkout["ap2_mandate"] = {
            "checkout_jwt": checkout_jwt,
            "checkout_jwt_hash": checkout_jwt_hash,
        }
        checkout["status"] = "requires_payment"
        self.store.save_checkout(checkout_id, checkout)
        return checkout

    async def finalize_from_ap2(
        self,
        checkout_id: str,
        order_id: str,
        checkout_receipt: str | None = None,
        payment_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark UCP checkout complete after AP2 flow already paid HEG (no double charge)."""
        checkout = self.store.get_checkout(checkout_id)
        if not checkout:
            raise ValueError(f"Checkout not found: {checkout_id}")
        checkout["status"] = "completed"
        checkout["order_id"] = order_id
        if checkout_receipt:
            checkout["checkout_receipt"] = checkout_receipt
        if payment_receipt:
            checkout["payment_receipt"] = payment_receipt
        self.store.save_checkout(checkout_id, checkout)
        return checkout

    def find_checkout_by_issue(self, issue_id: str) -> dict[str, Any] | None:
        return self.store.find_checkout_by_issue_id(issue_id)

    async def complete_checkout(self, checkout_id: str) -> dict[str, Any]:
        checkout = self.store.get_checkout(checkout_id)
        if not checkout:
            raise ValueError(f"Checkout not found: {checkout_id}")
        issue_id = checkout["issue_id"]
        confirm = await self.heg.confirm_presale(issue_id)
        if confirm.get("status") != "200":
            raise ValueError(confirm.get("msg") or "Presale confirm failed")
        order_id = confirm.get("orderId")
        pay = await self.heg.pay_order(order_id)
        if pay.get("status") != "200":
            raise ValueError(pay.get("msg") or "Payment failed")
        checkout["status"] = "completed"
        checkout["order_id"] = order_id
        checkout["payment_receipt"] = pay.get("paymentReceipt")
        self.store.save_checkout(checkout_id, checkout)
        return checkout

    def get_checkout(self, checkout_id: str) -> dict[str, Any] | None:
        return self.store.get_checkout(checkout_id)
