import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Playbook(Base):
    __tablename__ = "playbooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_code = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    trigger_incident_types = Column(JSONB, default=list)
    trigger_keywords = Column(JSONB, default=list)
    root_cause_hypothesis = Column(Text, nullable=True)
    confidence_score = Column(Integer, default=0)

    # Structured actions list
    # [{"step": 1, "type": "immediate", "action": "...", "expected_outcome": "..."}]
    actions = Column(JSONB, default=list)

    monitor_metrics = Column(JSONB, default=list)
    estimated_resolution_minutes = Column(Integer, default=30)

    # Now proper Boolean with server default
    is_active = Column(Boolean, default=True, nullable=False)

    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )