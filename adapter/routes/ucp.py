from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ucp_service import UcpService

router = APIRouter(prefix="", tags=["ucp"])
_service = UcpService()


class CatalogSearchRequest(BaseModel):
    query: str = Field(default="")
    price_cap: float | None = None


class CartCreateRequest(BaseModel):
    item_id: str
    qty: int = 1


class CheckoutCreateRequest(BaseModel):
    cart_id: str


class Ap2MandateAttachRequest(BaseModel):
    checkout_jwt: str
    checkout_jwt_hash: str


class CheckoutFinalizeRequest(BaseModel):
    order_id: str
    checkout_receipt: str | None = None
    payment_receipt: dict[str, Any] | None = None


@router.post("/catalog/search")
async def catalog_search(body: CatalogSearchRequest) -> dict[str, Any]:
    return await _service.catalog_search(body.query, price_cap=body.price_cap)


@router.post("/carts")
async def create_cart(body: CartCreateRequest) -> dict[str, Any]:
    try:
        return await _service.create_cart(body.item_id, qty=body.qty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/checkout-sessions")
async def create_checkout_session(body: CheckoutCreateRequest) -> dict[str, Any]:
    try:
        return await _service.create_checkout_session(body.cart_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/checkout-sessions/{checkout_id}")
async def get_checkout_session(checkout_id: str) -> dict[str, Any]:
    checkout = _service.get_checkout(checkout_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout not found")
    return checkout


@router.post("/checkout-sessions/{checkout_id}/ap2-mandate")
async def attach_ap2_mandate(checkout_id: str, body: Ap2MandateAttachRequest) -> dict[str, Any]:
    """Attach AP2 Checkout JWT to UCP checkout session (ap2_mandate extension)."""
    try:
        checkout = await _service.attach_ap2_checkout(
            checkout_id,
            body.checkout_jwt,
            body.checkout_jwt_hash,
        )
        return checkout
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/checkout-sessions/{checkout_id}/finalize")
async def finalize_checkout_session(checkout_id: str, body: CheckoutFinalizeRequest) -> dict[str, Any]:
    """Finalize UCP checkout after AP2 payment succeeded (sync state only)."""
    try:
        return await _service.finalize_from_ap2(
            checkout_id,
            body.order_id,
            checkout_receipt=body.checkout_receipt,
            payment_receipt=body.payment_receipt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/checkout-sessions/by-issue/{issue_id}")
async def get_checkout_by_issue(issue_id: str) -> dict[str, Any]:
    checkout = _service.find_checkout_by_issue(issue_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout not found for issue")
    return checkout


@router.post("/checkout-sessions/{checkout_id}/complete")
async def complete_checkout_session(checkout_id: str) -> dict[str, Any]:
    """Direct UCP complete (HEG confirm + pay) — used when AP2 is not involved."""
    try:
        return await _service.complete_checkout(checkout_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
