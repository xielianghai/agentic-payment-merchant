from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import log_operation
from services.common import dumps, loads, one, rows


def _hydrate(row: dict[str, Any]) -> dict[str, Any]:
    row["config_json"] = loads(row.get("config_json"))
    row["line_items_schema"] = loads(row.get("line_items_schema"))
    return row


async def list_capabilities(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM merchant_capabilities WHERE merchant_id=:merchant_id ORDER BY capability_id",
        {"merchant_id": merchant_id},
    )
    return [_hydrate(row) for row in result]


async def get_capability(session: AsyncSession, merchant_id: str, capability_id: str) -> dict[str, Any] | None:
    row = await one(
        session,
        "SELECT * FROM merchant_capabilities WHERE merchant_id=:merchant_id AND capability_id=:capability_id",
        {"merchant_id": merchant_id, "capability_id": capability_id},
    )
    return _hydrate(row) if row else None


async def create_capability(session: AsyncSession, merchant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            INSERT INTO merchant_capabilities
            (merchant_id, capability_id, version, status, descriptor, vertical, description_en, description_zh,
             schema_url, config_json, line_items_schema, registered_at)
            VALUES (:merchant_id, :capability_id, :version, :status, :descriptor, :vertical, :description_en,
                    :description_zh, :schema_url, :config_json, :line_items_schema, :now)
            """
        ),
        {
            "merchant_id": merchant_id,
            "capability_id": payload["capability_id"],
            "version": payload.get("version", "2026-01-23"),
            "status": payload.get("status", "DRAFT"),
            "descriptor": payload.get("descriptor"),
            "vertical": payload.get("vertical"),
            "description_en": payload.get("description_en"),
            "description_zh": payload.get("description_zh"),
            "schema_url": payload.get("schema_url"),
            "config_json": dumps(payload.get("config_json") or {}),
            "line_items_schema": dumps(payload.get("line_items_schema") or {}),
            "now": now,
        },
    )
    await log_operation(session, "capability.created", merchant_id=merchant_id, detail=payload)
    return await get_capability(session, merchant_id, payload["capability_id"]) or {}


async def update_capability(
    session: AsyncSession, merchant_id: str, capability_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    existing = await get_capability(session, merchant_id, capability_id)
    if not existing:
        raise ValueError("Capability not found")
    await session.execute(
        text(
            """
            UPDATE merchant_capabilities
            SET version=:version, status=:status, descriptor=:descriptor, vertical=:vertical,
                description_en=:description_en, description_zh=:description_zh, schema_url=:schema_url,
                config_json=:config_json, line_items_schema=:line_items_schema
            WHERE merchant_id=:merchant_id AND capability_id=:capability_id
            """
        ),
        {
            "merchant_id": merchant_id,
            "capability_id": capability_id,
            "version": payload.get("version", existing["version"]),
            "status": payload.get("status", existing["status"]),
            "descriptor": payload.get("descriptor", existing.get("descriptor")),
            "vertical": payload.get("vertical", existing.get("vertical")),
            "description_en": payload.get("description_en", existing.get("description_en")),
            "description_zh": payload.get("description_zh", existing.get("description_zh")),
            "schema_url": payload.get("schema_url", existing.get("schema_url")),
            "config_json": dumps(payload.get("config_json", existing.get("config_json") or {})),
            "line_items_schema": dumps(payload.get("line_items_schema", existing.get("line_items_schema") or {})),
        },
    )
    await log_operation(session, "capability.updated", merchant_id=merchant_id, detail={"capability_id": capability_id})
    return await get_capability(session, merchant_id, capability_id) or {}


async def delete_capability(session: AsyncSession, merchant_id: str, capability_id: str) -> None:
    existing = await get_capability(session, merchant_id, capability_id)
    if not existing:
        raise ValueError("Capability not found")
    await session.execute(
        text("DELETE FROM merchant_capabilities WHERE merchant_id=:merchant_id AND capability_id=:capability_id"),
        {"merchant_id": merchant_id, "capability_id": capability_id},
    )
    await log_operation(session, "capability.deleted", merchant_id=merchant_id, detail={"capability_id": capability_id})


async def validate_capability(session: AsyncSession, merchant_id: str, capability_id: str) -> dict[str, Any]:
    cap = await get_capability(session, merchant_id, capability_id)
    if not cap:
        raise ValueError("Capability not found")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(
        text(
            """
            UPDATE merchant_capabilities SET validated_at=:now, status='VALIDATED'
            WHERE merchant_id=:merchant_id AND capability_id=:capability_id
            """
        ),
        {"merchant_id": merchant_id, "capability_id": capability_id, "now": now},
    )
    await log_operation(session, "capability.validated", merchant_id=merchant_id, detail={"capability_id": capability_id})
    return await get_capability(session, merchant_id, capability_id) or {}


async def publish_capability(session: AsyncSession, merchant_id: str, capability_id: str) -> dict[str, Any]:
    cap = await get_capability(session, merchant_id, capability_id)
    if not cap:
        raise ValueError("Capability not found")
    await session.execute(
        text(
            """
            UPDATE merchant_capabilities SET status='PUBLISHED'
            WHERE merchant_id=:merchant_id AND capability_id=:capability_id
            """
        ),
        {"merchant_id": merchant_id, "capability_id": capability_id},
    )
    await log_operation(session, "capability.published", merchant_id=merchant_id, detail={"capability_id": capability_id})
    return await get_capability(session, merchant_id, capability_id) or {}


async def unpublish_capability(session: AsyncSession, merchant_id: str, capability_id: str) -> dict[str, Any]:
    await session.execute(
        text(
            """
            UPDATE merchant_capabilities SET status='OFFLINE'
            WHERE merchant_id=:merchant_id AND capability_id=:capability_id
            """
        ),
        {"merchant_id": merchant_id, "capability_id": capability_id},
    )
    await log_operation(session, "capability.offline", merchant_id=merchant_id, detail={"capability_id": capability_id})
    return await get_capability(session, merchant_id, capability_id) or {}
