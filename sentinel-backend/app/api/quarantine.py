from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.quarantine import QuarantinedPayload, QuarantineStatus
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.dependencies.auth import get_current_user, require_roles
from app.schemas.quarantine import (
    QuarantineResponse,
    QuarantineListResponse,
    ReprocessRequest,
    DiscardRequest,
)
from app.core.payload_validator import PayloadValidator
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/quarantine", tags=["Payload Health & Quarantine"])


@router.get("", response_model=QuarantineListResponse)
async def list_quarantined(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[QuarantineStatus] = Query(None),
    source_system: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all quarantined malformed payloads."""
    query = select(QuarantinedPayload).order_by(QuarantinedPayload.created_at.desc())

    if status:
        query = query.where(QuarantinedPayload.status == status)
    if source_system:
        query = query.where(QuarantinedPayload.source_system == source_system)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    # Counts per status
    quarantined_count = await db.scalar(
        select(func.count()).select_from(QuarantinedPayload).where(
            QuarantinedPayload.status == QuarantineStatus.quarantined
        )
    ) or 0
    reprocessed_count = await db.scalar(
        select(func.count()).select_from(QuarantinedPayload).where(
            QuarantinedPayload.status == QuarantineStatus.reprocessed
        )
    ) or 0
    discarded_count = await db.scalar(
        select(func.count()).select_from(QuarantinedPayload).where(
            QuarantinedPayload.status == QuarantineStatus.discarded
        )
    ) or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return QuarantineListResponse(
        items=[QuarantineResponse.model_validate(i) for i in items],
        total=total or 0,
        quarantined_count=quarantined_count,
        reprocessed_count=reprocessed_count,
        discarded_count=discarded_count,
    )


@router.get("/{payload_id}", response_model=QuarantineResponse)
async def get_quarantined_payload(
    payload_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """View a single quarantined payload with raw XML and validation errors."""
    result = await db.execute(
        select(QuarantinedPayload).where(
            QuarantinedPayload.id == uuid.UUID(payload_id)
        )
    )
    payload = result.scalar_one_or_none()
    if not payload:
        raise HTTPException(status_code=404, detail="Quarantined payload not found")
    return QuarantineResponse.model_validate(payload)


@router.post("/{payload_id}/reprocess")
async def reprocess_payload(
    payload_id: str,
    body: ReprocessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
    ),
):
    """
    Attempt reprocessing of a quarantined payload after correction.
    If corrected_payload is provided, uses that.
    Otherwise uses Sentinel's auto-corrected version.
    """
    result = await db.execute(
        select(QuarantinedPayload).where(
            QuarantinedPayload.id == uuid.UUID(payload_id)
        )
    )
    payload = result.scalar_one_or_none()
    if not payload:
        raise HTTPException(status_code=404, detail="Payload not found")

    if payload.status == QuarantineStatus.discarded:
        raise HTTPException(status_code=400, detail="Cannot reprocess a discarded payload")

    # Use provided correction or auto-corrected version
    payload_to_validate = body.corrected_payload or payload.corrected_payload or payload.raw_payload

    # Re-validate the payload
    validator = PayloadValidator()
    validation_result = validator.validate_xml(payload_to_validate)

    if not validation_result["is_valid"]:
        return {
            "success": False,
            "message": "Payload still contains validation errors after correction",
            "remaining_errors": validation_result["errors"],
            "reprocess_attempt": payload.reprocess_attempts + 1,
        }

    # Validation passed — mark as corrected/reprocessed
    if body.corrected_payload:
        payload.corrected_payload = body.corrected_payload

    payload.status = QuarantineStatus.reprocessed
    payload.reviewed_by = current_user.id
    payload.reprocess_attempts += 1
    payload.last_reprocess_at = datetime.now(timezone.utc)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action="quarantine.reprocessed",
        resource_type="quarantined_payload",
        resource_id=str(payload.id),
        description=f"Payload reprocessed successfully after {payload.reprocess_attempts} attempt(s)",
        after_state={"status": "reprocessed"},
    )
    db.add(audit)
    await db.commit()

    return {
        "success": True,
        "payload_id": payload_id,
        "status": "reprocessed",
        "message": "Payload validated and marked for resubmission to Oracle",
        "reprocess_attempts": payload.reprocess_attempts,
    }


@router.delete("/{payload_id}")
async def discard_payload(
    payload_id: str,
    body: DiscardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
    ),
):
    """Permanently discard a quarantined payload."""
    result = await db.execute(
        select(QuarantinedPayload).where(
            QuarantinedPayload.id == uuid.UUID(payload_id)
        )
    )
    payload = result.scalar_one_or_none()
    if not payload:
        raise HTTPException(status_code=404, detail="Payload not found")

    payload.status = QuarantineStatus.discarded
    payload.discarded_reason = body.reason
    payload.reviewed_by = current_user.id

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action="quarantine.discarded",
        resource_type="quarantined_payload",
        resource_id=str(payload.id),
        description=f"Payload discarded. Reason: {body.reason}",
        after_state={"status": "discarded", "reason": body.reason},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": "Payload discarded",
        "payload_id": payload_id,
        "reason": body.reason,
    }