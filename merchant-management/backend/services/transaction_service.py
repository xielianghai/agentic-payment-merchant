from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.common import loads, rows


async def list_transactions(
    session: AsyncSession,
    merchant_id: str | None = None,
    status: str | None = None,
    mandate_ref: str | None = None,
    receipt_ref: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM merchant_transactions WHERE 1=1"
    params: dict[str, Any] = {"limit": limit}
    if merchant_id:
        sql += " AND merchant_id=:merchant_id"
        params["merchant_id"] = merchant_id
    if status:
        sql += " AND status=:status"
        params["status"] = status
    if mandate_ref:
        sql += " AND mandate_ref=:mandate_ref"
        params["mandate_ref"] = mandate_ref
    if receipt_ref:
        sql += " AND receipt_ref=:receipt_ref"
        params["receipt_ref"] = receipt_ref
    sql += " ORDER BY occurred_at DESC LIMIT :limit"
    result = await rows(session, sql, params)
    for row in result:
        row["detail_json"] = loads(row.get("detail_json"))
        if row.get("amount") is not None:
            row["amount"] = float(row["amount"])
    return result


async def get_transaction_stats(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    txs = await list_transactions(session, merchant_id=merchant_id, limit=500)
    completed = [t for t in txs if t["status"] == "COMPLETED"]
    failed = [t for t in txs if t["status"] == "FAILED"]
    mandate_fail = [t for t in failed if (t.get("detail_json") or {}).get("error") == "mandate_verify_fail"]
    total_amount = sum(t.get("amount", 0) for t in completed)
    return {
        "total_transactions": len(txs),
        "completed_transactions": len(completed),
        "failed_transactions": len(failed),
        "mandate_verify_fail_count": len(mandate_fail),
        "total_amount": round(total_amount, 2),
        "receipt_index_count": len([t for t in txs if t.get("receipt_ref")]),
    }
