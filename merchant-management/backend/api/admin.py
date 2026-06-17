from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from services import (
    capability_service as cap_svc,
    certificate_service as cert_svc,
    export_service as export_svc,
    merchant_service as merchant_svc,
    onboarding_service as onboard_svc,
    reconciliation_service as recon_svc,
    transaction_service as tx_svc,
    trust_service as trust_svc,
)
from services.audit_service import list_operation_logs

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class KybSubmitRequest(BaseModel):
    legal_name: str
    registration_no: str
    country: str = "SG"
    vertical: str = "airline"
    contact_email: str
    documents_json: dict[str, Any] = Field(default_factory=dict)


class KybReviewRequest(BaseModel):
    approved: bool
    reviewer: str = "admin"
    reject_reason: str | None = None


class ContractSignRequest(BaseModel):
    signed_by: str


class CapabilityRequest(BaseModel):
    capability_id: str
    version: str = "2026-01-23"
    status: str = "DRAFT"
    descriptor: str | None = None
    vertical: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    schema_url: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    line_items_schema: dict[str, Any] = Field(default_factory=dict)


class CertificateIssueRequest(BaseModel):
    subject_cn: str | None = None


class CertificateRevokeRequest(BaseModel):
    reason: str = "admin_revoked"


class ExportRequest(BaseModel):
    requested_by: str = "admin"
    filters: dict[str, Any] = Field(default_factory=dict)


class CreateMerchantRequest(BaseModel):
    name: str
    display_name_en: str | None = None
    display_name_zh: str | None = None
    vertical: str = "airline"
    backend_base_url: str | None = None
    legal_name: str | None = None
    registration_no: str | None = None
    contact_email: str | None = None
    country: str = "SG"


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await merchant_svc.dashboard_stats(session)}


@router.get("/merchants")
async def list_merchants(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"code": "ok", "data": await merchant_svc.list_merchants(session, status=status)}


@router.post("/merchants")
async def create_merchant(
    body: CreateMerchantRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    merchant = await merchant_svc.create_merchant(session, body.model_dump())
    return {"code": "ok", "data": merchant, "message": "Merchant created successfully"}


@router.get("/merchants/{merchant_id}")
async def get_merchant(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    merchant = await merchant_svc.get_merchant(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {"code": "ok", "data": merchant}


@router.delete("/merchants/{merchant_id}")
async def delete_merchant(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        await merchant_svc.delete_merchant(session, merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": "ok", "data": None, "message": "Merchant deleted successfully"}


@router.get("/merchants/{merchant_id}/onboarding")
async def get_onboarding(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    kyb = await onboard_svc.get_kyb(session, merchant_id)
    contract = await onboard_svc.get_contract(session, merchant_id)
    tasks = await onboard_svc.list_onboarding_tasks(session, merchant_id)
    return {"code": "ok", "data": {"kyb": kyb, "contract": contract, "tasks": tasks}}


@router.get("/merchants/{merchant_id}/kyb")
async def get_kyb(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await onboard_svc.get_kyb(session, merchant_id)}


@router.post("/merchants/{merchant_id}/kyb")
async def submit_kyb(
    merchant_id: str, body: KybSubmitRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await onboard_svc.submit_kyb(session, merchant_id, body.model_dump())}


@router.post("/merchants/{merchant_id}/kyb/review")
async def review_kyb(
    merchant_id: str, body: KybReviewRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await onboard_svc.review_kyb(
        session, merchant_id, body.approved, body.reviewer, body.reject_reason
    )}


@router.get("/merchants/{merchant_id}/contract")
async def get_contract(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await onboard_svc.get_contract(session, merchant_id)}


@router.post("/merchants/{merchant_id}/contract/sign")
async def sign_contract(
    merchant_id: str, body: ContractSignRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await onboard_svc.sign_contract(session, merchant_id, body.signed_by)}


@router.post("/merchants/{merchant_id}/onboard")
async def onboard_merchant(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        merchant = await onboard_svc.onboard_merchant(session, merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": "ok", "data": merchant, "message": "Merchant onboarded successfully"}


@router.get("/merchants/{merchant_id}/capabilities")
async def get_capabilities(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await cap_svc.list_capabilities(session, merchant_id)}


@router.post("/merchants/{merchant_id}/capabilities")
async def create_capability(
    merchant_id: str, body: CapabilityRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await cap_svc.create_capability(session, merchant_id, body.model_dump())}


@router.put("/merchants/{merchant_id}/capabilities/{capability_id}")
async def update_capability(
    merchant_id: str, capability_id: str, body: CapabilityRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        data = await cap_svc.update_capability(session, merchant_id, capability_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": "ok", "data": data}


@router.delete("/merchants/{merchant_id}/capabilities/{capability_id}")
async def delete_capability(
    merchant_id: str, capability_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await cap_svc.delete_capability(session, merchant_id, capability_id)
    return {"code": "ok", "data": None}


@router.post("/merchants/{merchant_id}/capabilities/{capability_id}/validate")
async def validate_capability(
    merchant_id: str, capability_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        data = await cap_svc.validate_capability(session, merchant_id, capability_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": "ok", "data": data}


@router.post("/merchants/{merchant_id}/capabilities/{capability_id}/publish")
async def publish_capability(
    merchant_id: str, capability_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        data = await cap_svc.publish_capability(session, merchant_id, capability_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": "ok", "data": data}


@router.post("/merchants/{merchant_id}/capabilities/{capability_id}/offline")
async def offline_capability(
    merchant_id: str, capability_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await cap_svc.unpublish_capability(session, merchant_id, capability_id)}


@router.get("/merchants/{merchant_id}/trust/keys")
async def list_trust_keys(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await trust_svc.list_keys(session, merchant_id)}


@router.get("/merchants/{merchant_id}/trust/jwks")
async def get_jwks(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await trust_svc.get_jwks(session, merchant_id)}


@router.post("/merchants/{merchant_id}/trust/keys")
async def register_key(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await trust_svc.register_key(session, merchant_id)}


@router.post("/merchants/{merchant_id}/trust/keys/rotate")
async def rotate_key(
    merchant_id: str,
    actor: str = Query("merchant"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"code": "ok", "data": await trust_svc.rotate_key(session, merchant_id, actor=actor)}


@router.post("/merchants/{merchant_id}/trust/keys/{kid}/verify")
async def verify_key(
    merchant_id: str, kid: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        data = await trust_svc.verify_key(session, merchant_id, kid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": "ok", "data": data}


@router.get("/trust/expiry-alerts")
async def expiry_alerts(
    merchant_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"code": "ok", "data": await trust_svc.list_expiry_alerts(session, merchant_id)}


@router.get("/merchants/{merchant_id}/certificates")
async def list_certificates(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await cert_svc.list_certificates(session, merchant_id)}


@router.post("/merchants/{merchant_id}/certificates/issue")
async def issue_certificate(
    merchant_id: str,
    body: CertificateIssueRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    subject = body.subject_cn if body else None
    return {"code": "ok", "data": await cert_svc.issue_certificate(session, merchant_id, subject)}


@router.post("/merchants/{merchant_id}/certificates/{serial_no}/revoke")
async def revoke_certificate(
    merchant_id: str,
    serial_no: str,
    body: CertificateRevokeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"code": "ok", "data": await cert_svc.revoke_certificate(session, merchant_id, serial_no, body.reason)}


@router.post("/certificates/refresh-alerts")
async def refresh_cert_alerts(
    merchant_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"code": "ok", "data": await cert_svc.refresh_alerts(session, merchant_id)}


@router.get("/merchants/{merchant_id}/transactions")
async def list_transactions(
    merchant_id: str,
    status: str | None = Query(None),
    mandate_ref: str | None = Query(None),
    receipt_ref: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {
        "code": "ok",
        "data": await tx_svc.list_transactions(
            session, merchant_id=merchant_id, status=status, mandate_ref=mandate_ref, receipt_ref=receipt_ref, limit=limit
        ),
    }


@router.get("/merchants/{merchant_id}/transactions/stats")
async def transaction_stats(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await tx_svc.get_transaction_stats(session, merchant_id)}


@router.get("/merchants/{merchant_id}/monitoring")
async def monitoring(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await recon_svc.monitoring_overview(session, merchant_id)}


@router.get("/merchants/{merchant_id}/reconciliation/runs")
async def list_reconciliation_runs(
    merchant_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {"code": "ok", "data": await recon_svc.list_runs(session, merchant_id)}


@router.post("/merchants/{merchant_id}/reconciliation/run")
async def run_reconciliation(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await recon_svc.run_reconciliation(session, merchant_id)}


@router.get("/reconciliation/runs/{run_id}/items")
async def reconciliation_items(run_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await recon_svc.list_items(session, run_id)}


@router.get("/merchants/{merchant_id}/exports")
async def list_exports(merchant_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {"code": "ok", "data": await export_svc.list_exports(session, merchant_id)}


@router.post("/merchants/{merchant_id}/exports/dispute")
async def create_dispute_export(
    merchant_id: str, body: ExportRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return {
        "code": "ok",
        "data": await export_svc.create_dispute_export(
            session, merchant_id, body.requested_by, body.filters
        ),
    }


@router.get("/operation-logs")
async def operation_logs(
    merchant_id: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {
        "code": "ok",
        "data": await list_operation_logs(session, merchant_id=merchant_id, action=action, limit=limit),
    }


@router.get("/seed-templates")
async def seed_templates(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    merchants = await merchant_svc.list_merchants(session)
    return {"code": "ok", "data": {"templates": [m for m in merchants if m["status"] == "PENDING"]}}
