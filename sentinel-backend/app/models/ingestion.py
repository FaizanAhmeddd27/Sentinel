import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base
import enum


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SourceSystem(str, enum.Enum):
    core_banking = "core_banking"
    raast = "raast"
    wallet = "wallet"
    settlement = "settlement"


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Supabase Storage path
    file_size_bytes = Column(Integer, nullable=True)
    source_system = Column(SAEnum(SourceSystem), nullable=False)
    status = Column(SAEnum(JobStatus), default=JobStatus.pending)
    records_total = Column(Integer, default=0)
    records_processed = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    celery_task_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    job_logs = Column(JSON, default=list)
    uploaded_by = Column(UUID(as_uuid=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)