from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import log_operation, list_operation_logs
from services.common import dumps, loads, one, rows
from services.reconciliation_service import list_runs
from services.transaction_service import list_transactions


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = float(value)
        elif isinstance(value, dict):
            out[key] = _serialize_row(value)
        elif isinstance(value, list):
            out[key] = [_serialize_row(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


async def list_exports(session: AsyncSession, merchant_id: str) -> list[dict[str, Any]]:
    result = await rows(
        session,
        "SELECT * FROM export_jobs WHERE merchant_id=:merchant_id ORDER BY created_at DESC",
        {"merchant_id": merchant_id},
    )
    for row in result:
        row["filters_json"] = loads(row.get("filters_json"))
        row["artifact_summary_json"] = loads(row.get("artifact_summary_json"))
    return result


async def create_dispute_export(
    session: AsyncSession,
    merchant_id: str,
    requested_by: str = "admin",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    txs = await list_transactions(session, merchant_id=merchant_id, limit=200)
    logs = await list_operation_logs(session, merchant_id=merchant_id, limit=50)
    runs = await list_runs(session, merchant_id)

    artifact = {
        "merchant_id": merchant_id,
        "generated_at": now.isoformat(),
        "transaction_count": len(txs),
        "log_count": len(logs),
        "reconciliation_run_count": len(runs),
        "transactions": [_serialize_row(t) for t in txs[:20]],
        "recent_logs": [_serialize_row(l) for l in logs[:20]],
        "latest_reconciliation": _serialize_row(runs[0]) if runs else None,
        "bundle_format": "json",
    }

    result = await session.execute(
        text(
            """
            INSERT INTO export_jobs
            (merchant_id, export_type, status, requested_by, filters_json, artifact_summary_json, completed_at)
            VALUES (:merchant_id, 'dispute_bundle', 'COMPLETED', :requested_by, :filters_json, :artifact_summary, :now)
            """
        ),
        {
            "merchant_id": merchant_id,
            "requested_by": requested_by,
            "filters_json": dumps(filters or {}),
            "artifact_summary": dumps(artifact),
            "now": now,
        },
    )
    job_id = result.lastrowid
    await log_operation(
        session,
        "export.dispute_bundle",
        merchant_id=merchant_id,
        actor=requested_by,
        detail={"job_id": job_id},
    )
    job = await one(session, "SELECT * FROM export_jobs WHERE id=:id", {"id": job_id})
    if job:
        job["filters_json"] = loads(job.get("filters_json"))
        job["artifact_summary_json"] = loads(job.get("artifact_summary_json"))
    return job or {}
