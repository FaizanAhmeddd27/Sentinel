from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.playbook import Playbook
from app.models.incident import Incident, IncidentType
from app.models.user import User, UserRole
from app.dependencies.auth import get_current_user, require_roles
from typing import Optional, List, Any
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/playbooks", tags=["Playbook Engine"])


class PlaybookCreate(BaseModel):
    title: str
    description: Optional[str] = None
    trigger_incident_types: List[str] = []
    trigger_keywords: List[str] = []
    root_cause_hypothesis: Optional[str] = None
    confidence_score: int = 0
    actions: List[Any] = []
    monitor_metrics: List[str] = []
    estimated_resolution_minutes: int = 30


@router.get("")
async def list_playbooks(
    active_only: bool = Query(True),
    incident_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all operational playbooks."""
    query = select(Playbook).order_by(Playbook.usage_count.desc())
    if active_only:
        query = query.where(Playbook.is_active == 1)
    if incident_type:
        query = query.where(
            Playbook.trigger_incident_types.contains([incident_type])
        )
    result = await db.execute(query)
    playbooks = result.scalars().all()
    return {"items": [_serialize_playbook(p) for p in playbooks], "total": len(playbooks)}


@router.get("/match/{incident_id}")
async def match_playbook(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-match best playbook for a given incident pattern."""
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Get all active playbooks
    pb_result = await db.execute(
        select(Playbook).where(Playbook.is_active == 1)
    )
    playbooks = pb_result.scalars().all()

    # Score each playbook against the incident
    scored = []
    incident_type_str = incident.incident_type.value if incident.incident_type else ""

    for pb in playbooks:
        score = 0
        triggers = pb.trigger_incident_types or []

        # Exact incident type match
        if incident_type_str in triggers:
            score += 50

        # Keyword matching in title/description
        keywords = pb.trigger_keywords or []
        incident_text = f"{incident.title} {incident.description or ''}".lower()
        for kw in keywords:
            if kw.lower() in incident_text:
                score += 10

        # Source system match
        if incident.source_system and incident.source_system.lower() in str(triggers).lower():
            score += 20

        scored.append((pb, score))

    # Sort by score
    scored.sort(key=lambda x: x[1], reverse=True)

    if not scored or scored[0][1] == 0:
        return {"matched": False, "message": "No matching playbook found"}

    best_playbook, match_score = scored[0]

    # Update usage count
    best_playbook.usage_count = (best_playbook.usage_count or 0) + 1
    incident.recommended_playbook_id = best_playbook.id
    await db.commit()

    return {
        "matched": True,
        "playbook": _serialize_playbook(best_playbook),
        "match_score": match_score,
        "match_confidence": min(100, match_score),
    }


@router.get("/{playbook_id}")
async def get_playbook(
    playbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Playbook).where(Playbook.id == uuid.UUID(playbook_id))
    )
    pb = result.scalar_one_or_none()
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return _serialize_playbook(pb)


@router.post("")
async def create_playbook(
    data: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor])
    ),
):
    """Create new playbook. Admin/Supervisor only."""
    # Generate playbook code
    count_result = await db.scalar(select(func.count()).select_from(Playbook))
    code = f"P-{str(count_result + 1).zfill(3)}"

    pb = Playbook(
        playbook_code=code,
        title=data.title,
        description=data.description,
        trigger_incident_types=data.trigger_incident_types,
        trigger_keywords=data.trigger_keywords,
        root_cause_hypothesis=data.root_cause_hypothesis,
        confidence_score=data.confidence_score,
        actions=data.actions,
        monitor_metrics=data.monitor_metrics,
        estimated_resolution_minutes=data.estimated_resolution_minutes,
        created_by=current_user.id,
    )
    db.add(pb)
    await db.commit()
    await db.refresh(pb)
    return _serialize_playbook(pb)


@router.patch("/{playbook_id}")
async def update_playbook(
    playbook_id: str,
    data: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor])
    ),
):
    result = await db.execute(
        select(Playbook).where(Playbook.id == uuid.UUID(playbook_id))
    )
    pb = result.scalar_one_or_none()
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pb, field, value)
    pb.updated_by = current_user.id
    await db.commit()
    return _serialize_playbook(pb)


@router.delete("/{playbook_id}")
async def delete_playbook(
    playbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin])),
):
    result = await db.execute(
        select(Playbook).where(Playbook.id == uuid.UUID(playbook_id))
    )
    pb = result.scalar_one_or_none()
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook not found")
    pb.is_active = 0  # Soft delete
    await db.commit()
    return {"message": "Playbook deactivated"}


def _serialize_playbook(pb: Playbook) -> dict:
    return {
        "id": str(pb.id),
        "playbook_code": pb.playbook_code,
        "title": pb.title,
        "description": pb.description,
        "trigger_incident_types": pb.trigger_incident_types,
        "trigger_keywords": pb.trigger_keywords,
        "root_cause_hypothesis": pb.root_cause_hypothesis,
        "confidence_score": pb.confidence_score,
        "actions": pb.actions,
        "monitor_metrics": pb.monitor_metrics,
        "estimated_resolution_minutes": pb.estimated_resolution_minutes,
        "usage_count": pb.usage_count,
        "is_active": pb.is_active,
        "created_at": pb.created_at,
    }