import json
import uuid
from pathlib import Path
from typing import Any


class UcpSessionStore:
    def __init__(self, temp_db_dir: str) -> None:
        self.path = Path(temp_db_dir) / "ucp_sessions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"carts": {}, "checkouts": {}, "items": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"carts": {}, "checkouts": {}, "items": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_item(self, item_id: str, item: dict[str, Any]) -> None:
        data = self._load()
        data.setdefault("items", {})[item_id] = item
        self._save(data)

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return self._load().get("items", {}).get(item_id)

    def save_cart(self, cart_id: str, cart: dict[str, Any]) -> None:
        data = self._load()
        data.setdefault("carts", {})[cart_id] = cart
        self._save(data)

    def get_cart(self, cart_id: str) -> dict[str, Any] | None:
        carts = self._load().get("carts", {})
        if cart_id in carts:
            return carts[cart_id]
        for cart in carts.values():
            if cart.get("issue_id") == cart_id or cart.get("id") == cart_id:
                return cart
        return None

    def save_checkout(self, checkout_id: str, checkout: dict[str, Any]) -> None:
        data = self._load()
        data.setdefault("checkouts", {})[checkout_id] = checkout
        self._save(data)

    def get_checkout(self, checkout_id: str) -> dict[str, Any] | None:
        return self._load().get("checkouts", {}).get(checkout_id)

    def find_checkout_by_issue_id(self, issue_id: str) -> dict[str, Any] | None:
        for checkout in self._load().get("checkouts", {}).values():
            if checkout.get("issue_id") == issue_id:
                return checkout
        return None

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"
