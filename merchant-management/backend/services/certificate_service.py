import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import log_operation
from services.common import one, rows


def _compute_alert(not_after: datetime) -> str:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not_after <= now:
        return "EXPIRED"
    if not_after <= now + timedelta(days=30):
        return "EXPIRING_SOON"
    return "OK"


async def list_certificates(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    return await rows(
        session,
        "SELECT * FROM merchant_certificates WHERE merchant_id=:merchant_id ORDER BY created_at DESC",
        {"merchant_id": merchant_id},
    )


async def issue_certificate(session: AsyncSession, merchant_id: str, subject_cn: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    serial = f"CERT-{secrets.token_hex(8).upper()}"
    subject = subject_cn or merchant_id
    not_after = now + timedelta(days=365)
    alert = _compute_alert(not_after)
    cert_pem = (
        f"-----BEGIN CERTIFICATE-----\n"
        f"SERIAL:{serial}\nSUBJECT:{subject}\nISSUER:Agentic Payment Platform CA\n"
        f"NOT_BEFORE:{now.isoformat()}\nNOT_AFTER:{not_after.isoformat()}\n"
        f"-----END CERTIFICATE-----"
    )
    await session.execute(
        text(
            """
            INSERT INTO merchant_certificates
            (merchant_id, serial_no, subject_cn, status, not_before, not_after, alert_status, cert_pem)
            VALUES (:merchant_id, :serial_no, :subject_cn, 'ACTIVE', :not_before, :not_after, :alert_status, :cert_pem)
            """
        ),
        {
            "merchant_id": merchant_id,
            "serial_no": serial,
            "subject_cn": subject,
            "not_before": now,
            "not_after": not_after,
            "alert_status": alert,
            "cert_pem": cert_pem,
        },
    )
    await log_operation(session, "certificate.issued", merchant_id=merchant_id, detail={"serial_no": serial})
    return await one(
        session,
        "SELECT * FROM merchant_certificates WHERE serial_no=:serial_no",
        {"serial_no": serial},
    ) or {}


async def revoke_certificate(
    session: AsyncSession, merchant_id: str, serial_no: str, reason: str = "admin_revoked"
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchant_certificates
            SET status='REVOKED', revoked_at=:now, revoke_reason=:reason, alert_status='REVOKED'
            WHERE merchant_id=:merchant_id AND serial_no=:serial_no
            """
        ),
        {"merchant_id": merchant_id, "serial_no": serial_no, "now": now, "reason": reason},
    )
    await log_operation(
        session,
        "certificate.revoked",
        merchant_id=merchant_id,
        detail={"serial_no": serial_no, "reason": reason},
    )
    return await one(
        session,
        "SELECT * FROM merchant_certificates WHERE serial_no=:serial_no",
        {"serial_no": serial_no},
    ) or {}


async def delete_certificate(session: AsyncSession, merchant_id: str, serial_no: str) -> None:
    row = await one(
        session,
        "SELECT * FROM merchant_certificates WHERE merchant_id=:merchant_id AND serial_no=:serial_no",
        {"merchant_id": merchant_id, "serial_no": serial_no},
    )
    if not row:
        raise ValueError("Certificate not found")
    if row["status"] != "REVOKED":
        raise ValueError("Only revoked certificates can be deleted")
    await session.execute(
        text("DELETE FROM merchant_certificates WHERE merchant_id=:merchant_id AND serial_no=:serial_no"),
        {"merchant_id": merchant_id, "serial_no": serial_no},
    )
    await log_operation(
        session,
        "certificate.deleted",
        merchant_id=merchant_id,
        detail={"serial_no": serial_no},
    )


async def refresh_alerts(session: AsyncSession, merchant_id: str | None = None) -> list[dict[str, Any]]:
    certs = await rows(
        session,
        "SELECT id, merchant_id, not_after FROM merchant_certificates WHERE status='ACTIVE'"
        + (" AND merchant_id=:merchant_id" if merchant_id else ""),
        {"merchant_id": merchant_id} if merchant_id else {},
    )
    for cert in certs:
        alert = _compute_alert(cert["not_after"])
        await session.execute(
            text("UPDATE merchant_certificates SET alert_status=:alert WHERE id=:id"),
            {"alert": alert, "id": cert["id"]},
        )
    sql = "SELECT * FROM merchant_certificates WHERE status='ACTIVE'"
    params: dict[str, Any] = {}
    if merchant_id:
        sql += " AND merchant_id=:merchant_id"
        params["merchant_id"] = merchant_id
    sql += " ORDER BY not_after ASC"
    return await rows(session, sql, params)
