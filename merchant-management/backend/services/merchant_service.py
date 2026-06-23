from datetime import datetime, timezone
from typing import Any
import re
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from services.audit_service import log_operation
from services.common import dumps, loads, rows, one
from services.platform_urls import normalize_jwks_url

STATUS_PENDING = "PENDING"
STATUS_ACTIVE = "ACTIVE"
STATUS_DISABLED = "DISABLED"


async def dashboard_stats(session: AsyncSession) -> dict[str, Any]:
    stats = {}
    for key, sql in {
        "merchants_total": "SELECT COUNT(*) FROM merchants",
        "merchants_active": "SELECT COUNT(*) FROM merchants WHERE status='ACTIVE'",
        "merchants_disabled": "SELECT COUNT(*) FROM merchants WHERE status='DISABLED'",
        "onboarding_pending": "SELECT COUNT(*) FROM onboarding_tasks WHERE status='PENDING'",
        "capabilities_total": "SELECT COUNT(*) FROM merchant_capabilities",
        "kyb_pending": "SELECT COUNT(*) FROM merchant_kyb_reviews WHERE status='PENDING'",
        "contracts_pending": "SELECT COUNT(*) FROM merchant_contracts WHERE status='PENDING'",
        "cert_expiring": "SELECT COUNT(*) FROM merchant_certificates WHERE alert_status='EXPIRING_SOON'",
        "mandate_fail_total": (
            "SELECT COUNT(*) FROM merchant_transactions WHERE status='FAILED' "
            "AND JSON_EXTRACT(detail_json, '$.error') = 'mandate_verify_fail'"
        ),
    }.items():
        stats[key] = int((await session.execute(text(sql))).scalar_one() or 0)
    return stats


async def list_merchants(session: AsyncSession, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM merchants"
    params: dict[str, Any] = {}
    if status:
        sql += " WHERE status=:status"
        params["status"] = status
    sql += " ORDER BY created_at DESC"
    result = await rows(session, sql, params)
    for row in result:
        row["protocols"] = loads(row.get("protocols"))
        row["capabilities_json"] = loads(row.get("capabilities_json"))
        row["jwks_url"] = normalize_jwks_url(row.get("jwks_url"), row["id"])
    return result


async def get_merchant(session: AsyncSession, merchant_id: str) -> dict[str, Any] | None:
    row = await one(session, "SELECT * FROM merchants WHERE id=:id", {"id": merchant_id})
    if not row:
        return None
    row["protocols"] = loads(row.get("protocols"))
    row["capabilities_json"] = loads(row.get("capabilities_json"))
    row["jwks_url"] = normalize_jwks_url(row.get("jwks_url"), row["id"])
    return row


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:32] or "merchant"


def _default_capabilities(vertical: str) -> dict[str, bool]:
    base = {"catalog": True, "cart": True, "checkout": True, "order": True, "ap2_mandate": True}
    if vertical == "hotel":
        base["room_inventory"] = True
    elif vertical == "travel":
        base["package_bundle"] = True
    return base


async def create_merchant(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    base_id = payload.get("merchant_id") or _slugify(payload["name"])
    merchant_id = f"{base_id}_{secrets.token_hex(3)}"
    vertical = payload.get("vertical", "airline")
    settings = get_settings()
    backend_url = payload.get("backend_base_url") or settings.heg_flight_backend_url

    await session.execute(
        text(
            """
            INSERT INTO merchants
            (id, name, display_name_en, display_name_zh, status, protocols, backend_base_url,
             a2a_endpoint, mcp_server_path, capabilities_json, jwks_url)
            VALUES
            (:id, :name, :display_name_en, :display_name_zh, 'PENDING', :protocols, :backend_base_url,
             :a2a_endpoint, :mcp_server_path, :capabilities_json, :jwks_url)
            """
        ),
        {
            "id": merchant_id,
            "name": payload["name"],
            "display_name_en": payload.get("display_name_en") or payload["name"],
            "display_name_zh": payload.get("display_name_zh") or payload["name"],
            "protocols": dumps(payload.get("protocols") or ["A2A", "AP2", "UCP"]),
            "backend_base_url": backend_url,
            "a2a_endpoint": payload.get("a2a_endpoint") or f"{backend_url}/a2a/{merchant_id}",
            "mcp_server_path": payload.get("mcp_server_path") or settings.heg_mcp_server_path,
            "capabilities_json": dumps(_default_capabilities(vertical)),
            "jwks_url": payload.get("jwks_url") or f"{backend_url}/.well-known/jwks.json",
        },
    )

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
            "legal_name": payload.get("legal_name") or payload["name"],
            "registration_no": payload.get("registration_no") or f"REG-{secrets.token_hex(4).upper()}",
            "country": payload.get("country", "SG"),
            "vertical": vertical,
            "contact_email": payload.get("contact_email") or f"ops@{merchant_id}.demo",
            "documents_json": dumps(payload.get("documents_json") or {}),
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO merchant_contracts (merchant_id, contract_type, template_version, status, summary_json)
            VALUES (:merchant_id, 'platform_agreement', '2026-01', 'PENDING', :summary_json)
            """
        ),
        {
            "merchant_id": merchant_id,
            "summary_json": dumps(
                {
                    "title_en": "Agentic Payment Platform Agreement",
                    "title_zh": "Agentic 支付平台服务协议",
                }
            ),
        },
    )

    await log_operation(session, "merchant.created", merchant_id=merchant_id, detail={"name": payload["name"]})
    return await get_merchant(session, merchant_id) or {}


async def disable_merchant(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    merchant = await get_merchant(session, merchant_id)
    if not merchant:
        raise ValueError("Merchant not found")
    if merchant["status"] == STATUS_DISABLED:
        return merchant
    if merchant["status"] != STATUS_ACTIVE:
        raise ValueError("Only ACTIVE merchants can be disabled")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchants
            SET status=:status, updated_at=:now
            WHERE id=:id
            """
        ),
        {"id": merchant_id, "status": STATUS_DISABLED, "now": now},
    )
    await log_operation(
        session,
        "merchant.disabled",
        merchant_id=merchant_id,
        detail={"name": merchant["name"], "previous_status": merchant["status"]},
    )
    return await get_merchant(session, merchant_id) or {}


async def enable_merchant(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    merchant = await get_merchant(session, merchant_id)
    if not merchant:
        raise ValueError("Merchant not found")
    if merchant["status"] == STATUS_ACTIVE:
        return merchant
    if merchant["status"] != STATUS_DISABLED:
        raise ValueError("Only DISABLED merchants can be enabled")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchants
            SET status=:status, updated_at=:now
            WHERE id=:id
            """
        ),
        {"id": merchant_id, "status": STATUS_ACTIVE, "now": now},
    )
    await log_operation(
        session,
        "merchant.enabled",
        merchant_id=merchant_id,
        detail={"name": merchant["name"], "previous_status": merchant["status"]},
    )
    return await get_merchant(session, merchant_id) or {}


async def delete_merchant(session: AsyncSession, merchant_id: str) -> None:
    merchant = await get_merchant(session, merchant_id)
    if not merchant:
        raise ValueError("Merchant not found")

    await log_operation(
        session,
        "merchant.deleted",
        merchant_id=merchant_id,
        detail={"name": merchant["name"], "status": merchant["status"]},
    )

    await session.execute(
        text(
            """
            DELETE ri FROM reconciliation_items ri
            INNER JOIN reconciliation_runs rr ON ri.run_id = rr.id
            WHERE rr.merchant_id = :merchant_id
            """
        ),
        {"merchant_id": merchant_id},
    )

    for sql in [
        "DELETE FROM reconciliation_runs WHERE merchant_id=:merchant_id",
        "DELETE FROM export_jobs WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_transactions WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_certificates WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_trust_keys WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_kyb_reviews WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_contracts WHERE merchant_id=:merchant_id",
        "DELETE FROM merchant_capabilities WHERE merchant_id=:merchant_id",
        "DELETE FROM onboarding_tasks WHERE merchant_id=:merchant_id",
        "DELETE FROM operation_logs WHERE merchant_id=:merchant_id",
        "DELETE FROM merchants WHERE id=:merchant_id",
    ]:
        await session.execute(text(sql), {"merchant_id": merchant_id})


async def registry_merchants(session: AsyncSession) -> list[dict[str, Any]]:
    from services.capability_service import list_capabilities

    settings = get_settings()
    active = await list_merchants(session, status=STATUS_ACTIVE)
    registry = []
    for row in active:
        caps = await list_capabilities(session, row["id"])
        registry.append(
            {
                "merchant_id": row["id"],
                "name": row["name"],
                "display_name_en": row["display_name_en"],
                "display_name_zh": row["display_name_zh"],
                "protocols": row["protocols"],
                "backend_base_url": row["backend_base_url"],
                "a2a_endpoint": row["a2a_endpoint"],
                "ucp_profile_url": row["ucp_profile_url"] or settings.adapter_base_url + "/.well-known/ucp",
                "mcp_server_path": row["mcp_server_path"],
                "capabilities": [c["capability_id"] for c in caps if c.get("status") == "PUBLISHED"],
                "jwks_url": row["jwks_url"],
            }
        )
    return registry
