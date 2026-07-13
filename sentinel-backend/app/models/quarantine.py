import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base
import enum


class QuarantineStatus(str, enum.Enum):
    quarantined = "quarantined"
    reprocessed = "reprocessed"
    discarded = "discarded"
    corrected = "corrected"


class QuarantinedPayload(Base):
    __tablename__ = "quarantined_payloads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system = Column(String(100), nullable=False)
    original_filename = Column(String(255), nullable=True)
    raw_payload = Column(Text, nullable=False)
    corrected_payload = Column(Text, nullable=True)
    validation_errors = Column(JSONB, default=list)
    # Format: [{"field": "...", "error": "...", "value": "..."}]
    error_count = Column(Integer, default=0)
    status = Column(SAEnum(QuarantineStatus), default=QuarantineStatus.quarantined)
    incident_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reprocess_attempts = Column(Integer, default=0)
    last_reprocess_at = Column(DateTime(timezone=True), nullable=True)
    discarded_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)