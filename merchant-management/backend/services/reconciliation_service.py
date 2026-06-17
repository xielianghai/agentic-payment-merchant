from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import log_operation
from services.common import dumps, loads, one, rows
from services.transaction_service import list_transactions


async def list_runs(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM reconciliation_runs WHERE merchant_id=:merchant_id ORDER BY created_at DESC",
        {"merchant_id": merchant_id},
    )
    for row in result:
        row["file_summary_json"] = loads(row.get("file_summary_json"))
    return result


async def list_items(session: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM reconciliation_items WHERE run_id=:run_id ORDER BY id",
        {"run_id": run_id},
    )
    for row in result:
        row["detail_json"] = loads(row.get("detail_json"))
    return result


async def run_reconciliation(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    txs = await list_transactions(session, merchant_id=merchant_id, limit=500)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    matched = 0
    mismatch = 0
    mandate_fail = 0
    items: list[dict[str, Any]] = []

    for tx in txs:
        detail = tx.get("detail_json") or {}
        if tx["status"] == "FAILED" and detail.get("error") == "mandate_verify_fail":
            status = "MISMATCH"
            reason = "mandate_verify_fail"
            mandate_fail += 1
            mismatch += 1
        elif tx["status"] == "COMPLETED" and tx.get("receipt_ref"):
            status = "MATCHED"
            reason = None
            matched += 1
        elif tx["status"] == "FAILED":
            status = "MISMATCH"
            reason = "payment_failed"
            mismatch += 1
        else:
            status = "MISMATCH"
            reason = "missing_receipt"
            mismatch += 1
        items.append(
            {
                "order_id": tx["order_id"],
                "mandate_ref": tx.get("mandate_ref"),
                "receipt_ref": tx.get("receipt_ref"),
                "status": status,
                "mismatch_reason": reason,
                "detail_json": detail,
            }
        )

    file_summary = {
        "filename": f"reconciliation_{merchant_id}_{now.strftime('%Y%m%d_%H%M%S')}.json",
        "matched": matched,
        "mismatch": mismatch,
        "mandate_verify_fail": mandate_fail,
        "generated_at": now.isoformat(),
    }

    result = await session.execute(
        text(
            """
            INSERT INTO reconciliation_runs
            (merchant_id, status, total_items, matched_items, mismatch_items, mandate_verify_fail_count,
             file_summary_json, completed_at)
            VALUES (:merchant_id, 'COMPLETED', :total, :matched, :mismatch, :mandate_fail, :file_summary, :now)
            """
        ),
        {
            "merchant_id": merchant_id,
            "total": len(items),
            "matched": matched,
            "mismatch": mismatch,
            "mandate_fail": mandate_fail,
            "file_summary": dumps(file_summary),
            "now": now,
        },
    )
    run_id = result.lastrowid

    for item in items:
        await session.execute(
            text(
                """
                INSERT INTO reconciliation_items
                (run_id, merchant_id, order_id, mandate_ref, receipt_ref, status, mismatch_reason, detail_json)
                VALUES (:run_id, :merchant_id, :order_id, :mandate_ref, :receipt_ref, :status, :reason, :detail_json)
                """
            ),
            {
                "run_id": run_id,
                "merchant_id": merchant_id,
                "order_id": item["order_id"],
                "mandate_ref": item["mandate_ref"],
                "receipt_ref": item["receipt_ref"],
                "status": item["status"],
                "reason": item["mismatch_reason"],
                "detail_json": dumps(item["detail_json"]),
            },
        )

    await log_operation(session, "reconciliation.completed", merchant_id=merchant_id, detail=file_summary)
    run = await one(session, "SELECT * FROM reconciliation_runs WHERE id=:id", {"id": run_id})
    if run:
        run["file_summary_json"] = loads(run.get("file_summary_json"))
        run["items"] = await list_items(session, run_id)
    return run or {}


async def monitoring_overview(session: AsyncSession, merchant_id: str) -> dict[str, Any]:
    from services.transaction_service import get_transaction_stats

    stats = await get_transaction_stats(session, merchant_id)
    runs = await list_runs(session, merchant_id)
    latest = runs[0] if runs else None
    return {
        "merchant_id": merchant_id,
        "transaction_stats": stats,
        "latest_reconciliation": latest,
        "alerts": [
            {
                "type": "mandate_verify_fail",
                "count": stats["mandate_verify_fail_count"],
                "severity": "high" if stats["mandate_verify_fail_count"] > 0 else "ok",
            }
        ],
    }
