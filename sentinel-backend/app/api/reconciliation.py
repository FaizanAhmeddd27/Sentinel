from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.reconciliation import (
    ReconciliationBatch,
    ReconciliationException,
    ExceptionStatus,
)
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.dependencies.auth import get_current_user, require_roles
from app.schemas.reconciliation import (
    ReconciliationBatchResponse,
    ReconciliationBatchListResponse,
    ExceptionResponse,
    ExceptionListResponse,
    ExceptionReviewRequest,
)
from app.core.reconciliation_engine import ReconciliationEngine
from app.config import settings
from app.utils.storage import upload_file_to_storage
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation Assistant"])


@router.post("/upload-batch")
async def upload_reconciliation_batch(
    file: UploadFile = File(...),
    batch_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
    ),
):
    """
    Module 1 — Upload a reversal batch file.
    Triggers ReconciliationEngine to auto-classify exceptions.
    """
    if current_user.role == UserRole.compliance:
        raise HTTPException(status_code=403, detail="Compliance Officers have read-only access")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(status_code=413, detail=f"File too large: {size_mb:.1f}MB")

    # Upload to storage
    storage_path = f"reconciliation/{uuid.uuid4()}/{file.filename}"
    await upload_file_to_storage(content, storage_path, file.content_type)

    # Create batch record
    batch = ReconciliationBatch(
        batch_name=batch_name,
        file_path=storage_path,
        total_records=0,
        auto_matched=0,
        pending_review=0,
        status="processing",
        uploaded_by=current_user.id,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    # Run reconciliation engine
    engine = ReconciliationEngine(db)
    results = await engine.process_batch(
        batch_id=str(batch.id),
        file_content=content,
        filename=file.filename or "batch.csv",
    )

    # Update batch stats
    batch.total_records = results["total"]
    batch.auto_matched = results["auto_matched"]
    batch.pending_review = results["pending_review"]
    batch.status = "completed"
    batch.processed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "batch_id": str(batch.id),
        "batch_name": batch_name,
        "total_records": results["total"],
        "auto_matched": results["auto_matched"],
        "auto_match_rate": results["auto_match_rate"],
        "exceptions_requiring_review": results["pending_review"],
        "status": "completed",
        "message": f"Batch processed. {results['auto_matched']}/{results['total']} auto-matched. "
                   f"{results['pending_review']} require manual review.",
    }


@router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get batch detail and classification results."""
    result = await db.execute(
        select(ReconciliationBatch).where(
            ReconciliationBatch.id == uuid.UUID(batch_id)
        )
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    auto_match_rate = (
        round(batch.auto_matched / batch.total_records * 100, 1)
        if batch.total_records > 0 else 0.0
    )

    return {
        "id": str(batch.id),
        "batch_name": batch.batch_name,
        "total_records": batch.total_records,
        "auto_matched": batch.auto_matched,
        "auto_match_rate_percent": auto_match_rate,
        "pending_review": batch.pending_review,
        "approved": batch.approved,
        "dismissed": batch.dismissed,
        "status": batch.status,
        "processed_at": batch.processed_at,
        "created_at": batch.created_at,
    }


@router.get("/batches/{batch_id}/exceptions")
async def list_exceptions(
    batch_id: str,
    status: Optional[ExceptionStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List flagged exceptions requiring manual review for a batch."""
    query = (
        select(ReconciliationException)
        .where(ReconciliationException.batch_id == uuid.UUID(batch_id))
        .order_by(ReconciliationException.match_confidence.asc())
    )

    if status:
        query = query.where(ReconciliationException.exception_status == status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    # Count auto-matched vs pending
    auto_matched_count = await db.scalar(
        select(func.count()).select_from(ReconciliationException).where(
            ReconciliationException.batch_id == uuid.UUID(batch_id),
            ReconciliationException.exception_status == ExceptionStatus.auto_matched,
        )
    ) or 0

    pending_count = await db.scalar(
        select(func.count()).select_from(ReconciliationException).where(
            ReconciliationException.batch_id == uuid.UUID(batch_id),
            ReconciliationException.exception_status != ExceptionStatus.auto_matched,
        )
    ) or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    exceptions = result.scalars().all()

    return ExceptionListResponse(
        items=[ExceptionResponse.model_validate(e) for e in exceptions],
        total=total or 0,
        auto_matched_count=auto_matched_count,
        pending_review_count=pending_count,
    )


@router.patch("/exceptions/{exception_id}")
async def review_exception(
    exception_id: str,
    body: ExceptionReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
    ),
):
    """Approve or dismiss a flagged reconciliation exception."""
    result = await db.execute(
        select(ReconciliationException).where(
            ReconciliationException.id == uuid.UUID(exception_id)
        )
    )
    exception = result.scalar_one_or_none()
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")

    if exception.exception_status in [ExceptionStatus.approved, ExceptionStatus.dismissed]:
        raise HTTPException(status_code=400, detail="Exception already reviewed")

    new_status = (
        ExceptionStatus.approved
        if body.action == "approve"
        else ExceptionStatus.dismissed
    )
    exception.exception_status = new_status
    exception.reviewed_by = current_user.id
    exception.reviewed_at = datetime.now(timezone.utc)
    exception.review_notes = body.notes

    # Update batch counters
    batch_result = await db.execute(
        select(ReconciliationBatch).where(
            ReconciliationBatch.id == exception.batch_id
        )
    )
    batch = batch_result.scalar_one_or_none()
    if batch:
        if body.action == "approve":
            batch.approved = (batch.approved or 0) + 1
        else:
            batch.dismissed = (batch.dismissed or 0) + 1

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action=f"reconciliation.exception.{body.action}d",
        resource_type="reconciliation_exception",
        resource_id=str(exception.id),
        description=f"Exception {body.action}d. Notes: {body.notes or 'None'}",
        before_state={"status": exception.exception_status.value},
        after_state={"status": new_status.value, "notes": body.notes},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": f"Exception {body.action}d successfully",
        "exception_id": exception_id,
        "new_status": new_status,
        "reviewed_by": str(current_user.id),
        "reviewed_at": exception.reviewed_at.isoformat(),
    }