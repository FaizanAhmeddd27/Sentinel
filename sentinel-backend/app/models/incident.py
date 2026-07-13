import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base
import enum


class IncidentSeverity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class IncidentStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class IncidentType(str, enum.Enum):
    raast_timeout = "raast_timeout"
    retry_storm = "retry_storm"
    reversal_mismatch = "reversal_mismatch"
    malformed_payload = "malformed_payload"
    settlement_gap = "settlement_gap"
    wallet_degradation = "wallet_degradation"
    duplicate_transaction = "duplicate_transaction"
    unknown = "unknown"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    incident_type = Column(SAEnum(IncidentType), default=IncidentType.unknown)
    severity = Column(SAEnum(IncidentSeverity), default=IncidentSeverity.medium)
    status = Column(SAEnum(IncidentStatus), default=IncidentStatus.open)
    source_system = Column(String(100), nullable=True)

    # Related entities
    payment_lifecycle_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    assigned_to = Column(UUID(as_uuid=True), nullable=True)

    # Impact data
    transactions_affected = Column(Integer, default=0)
    customers_affected = Column(Integer, default=0)
    estimated_amount_pkr = Column(Numeric(15, 2), default=0)
    projected_transactions_25min = Column(Integer, default=0)

    # AI Summary
    ai_summary = Column(Text, nullable=True)
    ai_summary_generated_at = Column(DateTime(timezone=True), nullable=True)
    ai_model_used = Column(String(100), nullable=True)

    # Matched playbook
    recommended_playbook_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadata
    raw_incident_data = Column(JSONB, default=dict)
    resolution_notes = Column(Text, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    detected_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)