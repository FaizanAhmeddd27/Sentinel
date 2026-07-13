from pydantic import BaseModel
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from app.models.incident import IncidentSeverity, IncidentStatus, IncidentType


class IncidentResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    source_system: Optional[str]
    transactions_affected: int
    customers_affected: int
    estimated_amount_pkr: float
    ai_summary: Optional[str]
    ai_summary_generated_at: Optional[datetime]
    recommended_playbook_id: Optional[UUID]
    assigned_to: Optional[UUID]
    detected_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class IncidentListResponse(BaseModel):
    items: List[IncidentResponse]
    total: int
    page: int
    page_size: int


class IncidentAssignRequest(BaseModel):
    analyst_id: UUID


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    resolution_notes: Optional[str] = None


class AISummaryResponse(BaseModel):
    incident_id: UUID
    summary: str
    model_used: str
    generated_at: datetime