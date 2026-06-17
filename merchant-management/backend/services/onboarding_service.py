import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from services.audit_service import log_operation
from services.common import dumps, loads, one, rows


async def get_kyb(session: AsyncSession, merchant_id: str) -> dict[str, Any] | None:
    row = await one(session, "SELECT * FROM merchant_kyb_reviews WHERE merchant_id=:id", {"id": merchant_id})
    if row:
        row["documents_json"] = loads(row.get("documents_json"))
    return row


async def submit_kyb(session: AsyncSession, merchant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = await get_kyb(session, merchant_id)
    if existing:
        await session.execute(
            text(
                """
                UPDATE merchant_kyb_reviews
                SET legal_name=:legal_name, registration_no=:registration_no, country=:country,
                    vertical=:vertical, contact_email=:contact_email, documents_json=:documents_json,
                    status='PENDING', reject_reason=NULL, reviewer=NULL, reviewed_at=NULL
                WHERE merchant_id=:merchant_id
                """
            ),
            {
                "merchant_id": merchant_id,
                "legal_name": payload["legal_name"],
                "registration_no": payload["registration_no"],
                "country": payload.get("country", "SG"),
                "vertical": payload.get("vertical", "airline"),
                "contact_email": payload["contact_email"],
                "documents_json": dumps(payload.get("documents_json") or {}),
            },
        )
    else:
        await session.execute(
            text(
                """
                INSERT INTO merchant_kyb_reviews
                (merchant_id, legal_name, registration_no, country, vertical, contact_email, documents_json, status)
                VALUES (:merchant_id, :legal_name, :registration_no, :country, :vertical, :contact_email, :documents_json, 'PENDING')
                """
            ),
            {
                "merchant_id": merchant_id,
                "legal_name": payload["legal_name"],
                "registration_no": payload["registration_no"],
                "country": payload.get("country", "SG"),
                "vertical": payload.get("vertical", "airline"),
                "contact_email": payload["contact_email"],
                "documents_json": dumps(payload.get("documents_json") or {}),
            },
        )
    await log_operation(session, "kyb.submitted", merchant_id=merchant_id, detail=payload)
    return await get_kyb(session, merchant_id) or {}


async def review_kyb(
    session: AsyncSession,
    merchant_id: str,
    approved: bool,
    reviewer: str = "admin",
    reject_reason: str | None = None,
) -> dict[str, Any]:
    status = "APPROVED" if approved else "REJECTED"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchant_kyb_reviews
            SET status=:status, reviewer=:reviewer, reject_reason=:reject_reason, reviewed_at=:now
            WHERE merchant_id=:merchant_id
            """
        ),
        {
            "merchant_id": merchant_id,
            "status": status,
            "reviewer": reviewer,
            "reject_reason": reject_reason,
            "now": now,
        },
    )
    await log_operation(
        session,
        "kyb.approved" if approved else "kyb.rejected",
        merchant_id=merchant_id,
        actor=reviewer,
        detail={"reject_reason": reject_reason},
    )
    return await get_kyb(session, merchant_id) or {}


async def get_contract(session: AsyncSession, merchant_id: str) -> dict[str, Any] | None:
    row = await one(
        session,
        "SELECT * FROM merchant_contracts WHERE merchant_id=:id AND contract_type='platform_agreement'",
        {"id": merchant_id},
    )
    if row:
        row["summary_json"] = loads(row.get("summary_json"))
    return row


async def sign_contract(session: AsyncSession, merchant_id: str, signed_by: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    summary = {
        "title_en": "Agentic Payment Platform Agreement",
        "title_zh": "Agentic 支付平台服务协议",
        "signed_hash": hashlib.sha256(f"{merchant_id}:{signed_by}:{now.isoformat()}".encode()).hexdigest()[:16],
    }
    await session.execute(
        text(
            """
            UPDATE merchant_contracts
            SET status='SIGNED', signed_by=:signed_by, signed_at=:now, summary_json=:summary_json
            WHERE merchant_id=:merchant_id AND contract_type='platform_agreement'
            """
        ),
        {"merchant_id": merchant_id, "signed_by": signed_by, "now": now, "summary_json": dumps(summary)},
    )
    await log_operation(session, "contract.signed", merchant_id=merchant_id, actor=signed_by, detail=summary)
    return await get_contract(session, merchant_id) or {}


async def list_onboarding_tasks(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM onboarding_tasks WHERE merchant_id=:merchant_id ORDER BY id",
        {"merchant_id": merchant_id},
    )
    for row in result:
        row["detail_json"] = loads(row.get("detail_json"))
    return result


async def onboard_merchant(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    from services.merchant_service import get_merchant

    merchant = await get_merchant(session, merchant_id)
    if not merchant:
        raise ValueError("Merchant not found")
    if merchant["status"] == "ACTIVE":
        return merchant

    kyb = await get_kyb(session, merchant_id)
    contract = await get_contract(session, merchant_id)
    if not kyb or kyb["status"] != "APPROVED":
        raise ValueError("KYB review must be approved before onboarding")
    if not contract or contract["status"] != "SIGNED":
        raise ValueError("Contract must be signed before onboarding")

    settings = get_settings()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    steps = [
        ("validate_backend", {"url": merchant["backend_base_url"], "status": "ok"}),
        ("register_capabilities", {"capabilities": merchant["capabilities_json"]}),
        ("publish_ucp_profile", {"url": settings.adapter_base_url + "/.well-known/ucp"}),
        ("register_kid_jwks", {"jwks_url": merchant.get("jwks_url")}),
        ("activate_merchant", {"status": "ACTIVE", "merchant_id": merchant_id}),
    ]
    for step, detail in steps:
        await session.execute(
            text(
                """
                INSERT INTO onboarding_tasks (merchant_id, step, status, detail_json)
                VALUES (:merchant_id, :step, 'COMPLETED', :detail_json)
                """
            ),
            {"merchant_id": merchant_id, "step": step, "detail_json": dumps(detail)},
        )

    await session.execute(
        text(
            """
            UPDATE merchants
            SET status='ACTIVE', ucp_profile_url=:ucp_url, onboarded_at=:now, updated_at=:now
            WHERE id=:id
            """
        ),
        {
            "id": merchant_id,
            "ucp_url": settings.adapter_base_url + "/.well-known/ucp",
            "now": now,
        },
    )
    await log_operation(session, "merchant.onboarded", merchant_id=merchant_id, detail={"steps": len(steps)})
    return await get_merchant(session, merchant_id) or {}
