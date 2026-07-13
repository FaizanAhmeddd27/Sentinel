from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime


class PlaybookAction(BaseModel):
    step: int
    type: str = Field(..., pattern="^(immediate|short_term|escalation|monitor)$")
    action: str
    expected_outcome: Optional[str] = None
    command: Optional[str] = None
    contact: Optional[str] = None


class PlaybookCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=500)
    description: Optional[str] = None
    trigger_incident_types: List[str] = []
    trigger_keywords: List[str] = []
    root_cause_hypothesis: Optional[str] = None
    confidence_score: int = Field(0, ge=0, le=100)
    actions: List[Any] = []
    monitor_metrics: List[str] = []
    estimated_resolution_minutes: int = Field(30, ge=1, le=1440)


class PlaybookUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=500)
    description: Optional[str] = None
    trigger_incident_types: Optional[List[str]] = None
    trigger_keywords: Optional[List[str]] = None
    root_cause_hypothesis: Optional[str] = None
    confidence_score: Optional[int] = Field(None, ge=0, le=100)
    actions: Optional[List[Any]] = None
    monitor_metrics: Optional[List[str]] = None
    estimated_resolution_minutes: Optional[int] = None


class PlaybookResponse(BaseModel):
    id: UUID
    playbook_code: str
    title: str
    description: Optional[str] = None
    trigger_incident_types: List[str]
    trigger_keywords: List[str]
    root_cause_hypothesis: Optional[str] = None
    confidence_score: int
    actions: List[Any]
    monitor_metrics: List[str]
    estimated_resolution_minutes: int
    usage_count: int
    is_active: int
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PlaybookListResponse(BaseModel):
    items: List[PlaybookResponse]
    total: int


class PlaybookMatchResponse(BaseModel):
    matched: bool
    playbook: Optional[PlaybookResponse] = None
    match_score: int = 0
    match_confidence: int = 0
    matched_on: List[str] = []         # which fields triggered the match
    message: Optional[str] = None