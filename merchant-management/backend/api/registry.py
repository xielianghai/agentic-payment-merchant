from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from services import merchant_service as svc

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


@router.get("/merchants")
async def registry_merchants(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await svc.registry_merchants(session)}


@router.get("/merchants/{merchant_id}")
async def registry_merchant(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    merchants = await svc.registry_merchants(session)
    for m in merchants:
        if m["merchant_id"] == merchant_id:
            return {"code": "ok", "data": m}
    return {"code": "not_found", "data": None}
