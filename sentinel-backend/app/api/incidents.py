from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.incident import Incident, IncidentStatus, IncidentSeverity, IncidentType
from app.models.user import User, UserRole
from app.dependencies.auth import get_current_user, require_roles
from app.tasks.ai_tasks import generate_incident_summary
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("")
async def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[IncidentStatus] = None,
    severity: Optional[IncidentSeverity] = None,
    source_system: Optional[str] = None,
    incident_type: Optional[IncidentType] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    assigned_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List incidents with filters and pagination."""
    query = select(Incident).order_by(Incident.detected_at.desc())

    filters = []
    if status:
        filters.append(Incident.status == status)
    if severity:
        filters.append(Incident.severity == severity)
    if source_system:
        filters.append(Incident.source_system == source_system)
    if incident_type:
        filters.append(Incident.incident_type == incident_type)
    if date_from:
        filters.append(Incident.detected_at >= date_from)
    if date_to:
        filters.append(Incident.detected_at <= date_to)
    if assigned_to:
        filters.append(Incident.assigned_to == uuid.UUID(assigned_to))

    if filters:
        query = query.where(and_(*filters))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    incidents = result.scalars().all()

    return {
        "items": [_serialize_incident(i) for i in incidents],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full incident detail including correlated timeline and AI summary."""
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return {
        **_serialize_incident(incident),
        "raw_incident_data": incident.raw_incident_data,
        "resolution_notes": incident.resolution_notes,
        "resolved_by": str(incident.resolved_by) if incident.resolved_by else None,
        "resolved_at": incident.resolved_at,
    }


@router.patch("/{incident_id}/assign")
async def assign_incident(
    incident_id: str,
    analyst_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor])
    ),
):
    """Assign incident to an analyst. Supervisor/Admin only."""
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.assigned_to = uuid.UUID(analyst_id)
    incident.status = IncidentStatus.in_progress
    await db.commit()

    return {"message": "Incident assigned", "incident_id": incident_id, "assigned_to": analyst_id}


@router.patch("/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    status: IncidentStatus,
    resolution_notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update incident status."""
    # Compliance officers cannot modify incidents
    if current_user.role == UserRole.compliance:
        raise HTTPException(status_code=403, detail="Compliance officers have read-only access")

    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = status
    if resolution_notes:
        incident.resolution_notes = resolution_notes
    if status == IncidentStatus.resolved:
        incident.resolved_by = current_user.id
        incident.resolved_at = datetime.utcnow()

    await db.commit()
    return {"message": "Status updated", "new_status": status}


@router.post("/{incident_id}/ai-summary")
async def trigger_ai_summary(
    incident_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger or regenerate AI summary for an incident via Celery task."""
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Trigger Celery task
    task = generate_incident_summary.delay(incident_id)

    return {
        "message": "AI summary generation triggered",
        "incident_id": incident_id,
        "task_id": task.id,
        "note": "Summary will be available in 2-5 seconds. Poll GET /incidents/{id}",
    }


def _serialize_incident(incident: Incident) -> dict:
    return {
        "id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "status": incident.status,
        "source_system": incident.source_system,
        "transactions_affected": incident.transactions_affected,
        "customers_affected": incident.customers_affected,
        "estimated_amount_pkr": float(incident.estimated_amount_pkr or 0),
        "projected_transactions_25min": incident.projected_transactions_25min,
        "ai_summary": incident.ai_summary,
        "ai_summary_generated_at": incident.ai_summary_generated_at,
        "ai_model_used": incident.ai_model_used,
        "recommended_playbook_id": str(incident.recommended_playbook_id) if incident.recommended_playbook_id else None,
        "assigned_to": str(incident.assigned_to) if incident.assigned_to else None,
        "payment_lifecycle_id": str(incident.payment_lifecycle_id) if incident.payment_lifecycle_id else None,
        "detected_at": incident.detected_at,
    }