from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from app.models.quarantine import QuarantineStatus


class ValidationError(BaseModel):
    field: str
    error: str
    value: Optional[Any] = None
    line_number: Optional[int] = None


class QuarantineResponse(BaseModel):
    id: UUID
    source_system: str
    original_filename: Optional[str] = None
    raw_payload: str
    corrected_payload: Optional[str] = None
    validation_errors: List[Any]
    error_count: int
    status: QuarantineStatus
    incident_id: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    reprocess_attempts: int
    last_reprocess_at: Optional[datetime] = None
    discarded_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class QuarantineListResponse(BaseModel):
    items: List[QuarantineResponse]
    total: int
    quarantined_count: int
    reprocessed_count: int
    discarded_count: int


class ReprocessRequest(BaseModel):
    corrected_payload: Optional[str] = Field(
        None,
        description="Provide corrected XML/payload. If omitted, Sentinel uses auto-corrected version."
    )
    notes: Optional[str] = None


class DiscardRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)