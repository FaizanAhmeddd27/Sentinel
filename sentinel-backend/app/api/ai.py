from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.incident import Incident
from app.models.user import User, UserRole
from app.dependencies.auth import get_current_user, require_roles
from app.core.ai_summarizer import AISummarizer
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/ai", tags=["AI — Incident Summary"])


class ManualSummarizeRequest(BaseModel):
    """Direct call to AI summarizer with custom structured data."""
    incident_data: dict
    model_preference: Optional[str] = None


@router.post("/summarize")
async def summarize_incident(
    body: ManualSummarizeRequest,
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
    ),
):
    """
    Internal endpoint — sends structured incident JSON to Groq API.
    Returns plain-English ops-bridge-ready summary.
    Called directly or via Celery task.
    """
    summarizer = AISummarizer()

    try:
        summary, model_used = await summarizer.generate_summary(body.incident_data)
        return {
            "summary": summary,
            "model_used": model_used,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "character_count": len(summary),
            "note": "All figures sourced from Sentinel telemetry — not inferred.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI summarization failed: {str(e)}. Check GROQ_API_KEY.",
        )


@router.post("/summarize/{incident_id}")
async def summarize_by_incident_id(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch incident from DB and generate AI summary inline (synchronous path).
    For when you need the result immediately rather than via Celery.
    """
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident_data = {
        "incident_id": str(incident.id),
        "title": incident.title,
        "incident_type": incident.incident_type.value if incident.incident_type else "unknown",
        "severity": incident.severity.value if incident.severity else "medium",
        "source_system": incident.source_system,
        "transactions_affected": incident.transactions_affected,
        "customers_affected": incident.customers_affected,
        "estimated_amount_pkr": float(incident.estimated_amount_pkr or 0),
        "projected_transactions_25min": incident.projected_transactions_25min,
        "detected_at": str(incident.detected_at),
        "description": incident.description,
    }

    summarizer = AISummarizer()
    summary, model_used = await summarizer.generate_summary(incident_data)

    # Persist to incident record
    incident.ai_summary = summary
    incident.ai_summary_generated_at = datetime.now(timezone.utc)
    incident.ai_model_used = model_used
    await db.commit()

    return {
        "incident_id": incident_id,
        "summary": summary,
        "model_used": model_used,
        "generated_at": incident.ai_summary_generated_at.isoformat(),
    }