from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.incident import Incident
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.core.impact_engine import ImpactEngine
import uuid

router = APIRouter(prefix="/impact", tags=["Incident Impact Engine"])


@router.get("/{incident_id}")
async def get_incident_impact(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Module 2 — Incident Impact Engine.

    Returns projected business impact using rolling 90-day baseline:
    - Transactions currently affected
    - Projected transactions at risk (25-minute window)
    - Customers affected
    - Estimated settlement impact in PKR
    - Timeline of escalation
    """
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    engine = ImpactEngine(db)
    impact = await engine.calculate(incident)
    return impact