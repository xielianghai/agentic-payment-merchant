import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import log_operation
from services.common import dumps, loads, one, rows


def _hydrate(row: dict[str, Any]) -> dict[str, Any]:
    row["public_jwk_json"] = loads(row.get("public_jwk_json"))
    return row


def _make_jwk(kid: str) -> dict[str, Any]:
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": secrets.token_hex(64),
        "e": "AQAB",
    }


def _fingerprint(jwk: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(jwk).encode()).hexdigest()[:32]


async def list_keys(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM merchant_trust_keys WHERE merchant_id=:merchant_id ORDER BY created_at DESC",
        {"merchant_id": merchant_id},
    )
    return [_hydrate(row) for row in result]


async def get_jwks(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    keys = await list_keys(session, merchant_id)
    active = [k for k in keys if k["status"] == "ACTIVE"]
    return {"keys": [k["public_jwk_json"] for k in active]}


async def register_key(session: AsyncSession, merchant_id: str, actor: str = "admin") -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    kid = f"{merchant_id}-{now.strftime('%Y%m%d%H%M%S')}"
    jwk = _make_jwk(kid)
    fingerprint = _fingerprint(jwk)
    expires_at = now + timedelta(days=365)
    await session.execute(
        text(
            """
            INSERT INTO merchant_trust_keys
            (merchant_id, kid, alg, public_jwk_json, source, status, fingerprint, expires_at, last_verified_at)
            VALUES (:merchant_id, :kid, 'RS256', :public_jwk_json, 'platform', 'ACTIVE', :fingerprint, :expires_at, :now)
            """
        ),
        {
            "merchant_id": merchant_id,
            "kid": kid,
            "public_jwk_json": dumps(jwk),
            "fingerprint": fingerprint,
            "expires_at": expires_at,
            "now": now,
        },
    )
    await session.execute(
        text("UPDATE merchants SET jwks_url=:url WHERE id=:id"),
        {"id": merchant_id, "url": f"/api/v1/admin/merchants/{merchant_id}/trust/jwks"},
    )
    await log_operation(session, "trust.key.registered", merchant_id=merchant_id, actor=actor, detail={"kid": kid})
    row = await one(
        session,
        "SELECT * FROM merchant_trust_keys WHERE merchant_id=:merchant_id AND kid=:kid",
        {"merchant_id": merchant_id, "kid": kid},
    )
    return _hydrate(row) if row else {}


async def rotate_key(session: AsyncSession, merchant_id: str, actor: str = "merchant") -> dict[str, Any]:
    await session.execute(
        text(
            """
            UPDATE merchant_trust_keys SET status='ROTATED'
            WHERE merchant_id=:merchant_id AND status='ACTIVE'
            """
        ),
        {"merchant_id": merchant_id},
    )
    new_key = await register_key(session, merchant_id, actor=actor)
    await log_operation(session, "trust.key.rotated", merchant_id=merchant_id, actor=actor, detail={"kid": new_key.get("kid")})
    return new_key


async def verify_key(session: AsyncSession, merchant_id: str, kid: str) -> dict[str, Any]:
    row = await one(
        session,
        "SELECT * FROM merchant_trust_keys WHERE merchant_id=:merchant_id AND kid=:kid",
        {"merchant_id": merchant_id, "kid": kid},
    )
    if not row:
        raise ValueError("Key not found")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchant_trust_keys SET last_verified_at=:now
            WHERE merchant_id=:merchant_id AND kid=:kid
            """
        ),
        {"merchant_id": merchant_id, "kid": kid, "now": now},
    )
    await log_operation(session, "trust.key.verified", merchant_id=merchant_id, detail={"kid": kid})
    updated = await one(
        session,
        "SELECT * FROM merchant_trust_keys WHERE merchant_id=:merchant_id AND kid=:kid",
        {"merchant_id": merchant_id, "kid": kid},
    )
    return _hydrate(updated) if updated else {}


async def list_expiry_alerts(session: AsyncSession, merchant_id: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT merchant_id, kid, expires_at, status,
               CASE
                   WHEN expires_at <= NOW() THEN 'EXPIRED'
                   WHEN expires_at <= DATE_ADD(NOW(), INTERVAL 30 DAY) THEN 'EXPIRING_SOON'
                   ELSE 'OK'
               END AS alert_status
        FROM merchant_trust_keys
        WHERE status='ACTIVE'
    """
    params: dict[str, Any] = {}
    if merchant_id:
        sql += " AND merchant_id=:merchant_id"
        params["merchant_id"] = merchant_id
    sql += " ORDER BY expires_at ASC"
    return await rows(session, sql, params)
