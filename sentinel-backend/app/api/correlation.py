from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.transaction import RawTransaction, PaymentLifecycle
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.core.correlation_engine import CorrelationEngine
import uuid

router = APIRouter(prefix="/correlation", tags=["Correlation Engine"])


@router.post("/run")
async def run_correlation(
    job_id: str = None,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger correlation batch on ingested data."""
    from app.tasks.correlation_tasks import run_correlation as celery_run
    task = celery_run.delay(job_id)
    return {
        "message": "Correlation job triggered",
        "task_id": task.id,
        "job_id": job_id,
    }


@router.get("/graph/{transaction_id}")
async def get_payment_graph(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Payment Lifecycle Graph for a transaction ID (any source system ID)."""

    # Search across all identifier maps
    result = await db.execute(select(PaymentLifecycle))
    lifecycles = result.scalars().all()

    # Find lifecycle containing this transaction ID
    matched = None
    for lc in lifecycles:
        id_map = lc.identifier_map or {}
        if transaction_id in id_map.values() or transaction_id == lc.canonical_id:
            matched = lc
            break

    if not matched:
        # Also search raw transactions
        raw_result = await db.execute(
            select(RawTransaction).where(
                RawTransaction.source_transaction_id == transaction_id
            )
        )
        raw = raw_result.scalar_one_or_none()
        if raw and raw.correlation_group_id:
            lc_result = await db.execute(
                select(PaymentLifecycle).where(
                    PaymentLifecycle.id == raw.correlation_group_id
                )
            )
            matched = lc_result.scalar_one_or_none()

    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"No payment lifecycle found for transaction ID: {transaction_id}",
        )

    return {
        "canonical_id": matched.canonical_id,
        "amount": float(matched.amount or 0),
        "currency": matched.currency,
        "status": matched.status,
        "identifier_map": matched.identifier_map,
        "lifecycle_graph": matched.lifecycle_graph,
        "timeline_events": matched.timeline_events,
        "correlation_confidence": float(matched.correlation_confidence or 0),
        "initiated_at": matched.initiated_at,
        "completed_at": matched.completed_at,
    }