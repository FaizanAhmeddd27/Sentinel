import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AuditLog(Base):
    """
    Immutable audit trail for all system actions.
    Compliance Officer read-only view.
    Records every state change, file ingestion, role change, 
    incident resolution, and reconciliation decision.
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who did it
    actor_id = Column(UUID(as_uuid=True), nullable=True)        # user who triggered action
    actor_email = Column(String(255), nullable=True)            # denormalized for audit reads
    actor_role = Column(String(50), nullable=True)

    # What happened
    action = Column(String(100), nullable=False)                 # e.g. "incident.resolved"
    resource_type = Column(String(100), nullable=True)          # e.g. "incident"
    resource_id = Column(String(255), nullable=True)            # UUID of affected resource

    # Detail
    description = Column(Text, nullable=True)
    before_state = Column(JSONB, nullable=True)                 # snapshot before change
    after_state = Column(JSONB, nullable=True)                  # snapshot after change
    event_metadata = Column("metadata", JSONB, nullable=True)         # extra context

    # Request context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_id = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    # No updated_at — audit logs are immutable