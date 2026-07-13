import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base
import enum


class TransactionStatus(str, enum.Enum):
    created = "created"
    submitted = "submitted"
    processing = "processing"
    completed = "completed"
    reversed = "reversed"
    failed = "failed"
    pending_reconciliation = "pending_reconciliation"


class RawTransaction(Base):
    """Raw parsed records from ingested files."""
    __tablename__ = "raw_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system = Column(String(50), nullable=False)
    source_transaction_id = Column(String(255), nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="PKR")
    account_from = Column(String(100), nullable=True)
    account_to = Column(String(100), nullable=True)
    transaction_timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), nullable=True)
    raw_data = Column(JSONB, nullable=True)
    ingestion_job_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    correlation_group_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PaymentLifecycle(Base):
    """Correlated payment object spanning multiple source systems."""
    __tablename__ = "payment_lifecycles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_id = Column(String(255), unique=True, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="PKR")
    account_from = Column(String(100), nullable=True)
    account_to = Column(String(100), nullable=True)
    initiated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # ✅ FIXED: was Column(Column(...)) — now correct String enum storage
    status = Column(String(50), default="pending_reconciliation")

    # Identifier map: {"oracle": "TXN-001", "raast": "RAAST-001", ...}
    identifier_map = Column(JSONB, default=dict)

    # Graph stored as JSONB: {"nodes": [...], "edges": [...]}
    lifecycle_graph = Column(JSONB, default=dict)

    # Timeline events list
    timeline_events = Column(JSONB, default=list)

    correlation_confidence = Column(Numeric(5, 2), default=0.0)

    source_count = Column(Integer, default=1)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )