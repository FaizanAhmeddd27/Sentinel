from pydantic import BaseModel
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from app.models.ingestion import JobStatus, SourceSystem


class IngestionJobCreate(BaseModel):
    source_system: SourceSystem


class IngestionJobResponse(BaseModel):
    id: UUID
    filename: str
    source_system: SourceSystem
    status: JobStatus
    records_total: int
    records_processed: int
    records_failed: int
    celery_task_id: Optional[str]
    error_message: Optional[str]
    job_logs: List[Any]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class IngestionJobListResponse(BaseModel):
    items: List[IngestionJobResponse]
    total: int
    page: int
    page_size: int