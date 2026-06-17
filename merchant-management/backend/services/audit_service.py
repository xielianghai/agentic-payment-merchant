from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import dumps, loads, rows


async def log_operation(
    session: AsyncSession,
    action: str,
    merchant_id: str | None = None,
    actor: str = "admin",
    detail: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO operation_logs (merchant_id, action, actor, detail_json)
            VALUES (:merchant_id, :action, :actor, :detail_json)
            """
        ),
        {
            "merchant_id": merchant_id,
            "action": action,
            "actor": actor,
            "detail_json": dumps(detail or {}),
        },
    )


async def list_operation_logs(
    session: AsyncSession,
    merchant_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM operation_logs WHERE 1=1"
    params: dict[str, Any] = {"limit": limit}
    if merchant_id:
        sql += " AND merchant_id=:merchant_id"
        params["merchant_id"] = merchant_id
    if action:
        sql += " AND action=:action"
        params["action"] = action
    sql += " ORDER BY created_at DESC LIMIT :limit"
    result = await rows(session, sql, params)
    for row in result:
        row["detail_json"] = loads(row.get("detail_json"))
    return result
