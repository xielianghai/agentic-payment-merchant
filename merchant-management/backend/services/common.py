import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


async def rows(session: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = (await session.execute(text(sql), params or {})).mappings().all()
    return [dict(row) for row in result]


async def one(session: AsyncSession, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    row = (await session.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


JSON_FIELDS = {
    "protocols",
    "capabilities_json",
    "config_json",
    "detail_json",
    "documents_json",
    "summary_json",
    "public_jwk_json",
    "line_items_schema",
    "file_summary_json",
    "filters_json",
    "artifact_summary_json",
}
