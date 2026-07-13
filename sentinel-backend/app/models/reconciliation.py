import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base
import enum


class ExceptionStatus(str, enum.Enum):
    auto_matched = "auto_matched"
    pending_confirmation = "pending_confirmation"
    likely_duplicate = "likely_duplicate"
    missing_settlement = "missing_settlement"
    manual_review = "manual_review"
    approved = "approved"
    dismissed = "dismissed"


class ReconciliationBatch(Base):
    __tablename__ = "reconciliation_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    total_records = Column(Integer, default=0)
    auto_matched = Column(Integer, default=0)
    pending_review = Column(Integer, default=0)
    approved = Column(Integer, default=0)
    dismissed = Column(Integer, default=0)
    status = Column(String(50), default="processing")
    uploaded_by = Column(UUID(as_uuid=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReconciliationException(Base):
    __tablename__ = "reconciliation_exceptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    exception_status = Column(SAEnum(ExceptionStatus), nullable=False)
    oracle_ref = Column(String(255), nullable=True)
    raast_ref = Column(String(255), nullable=True)
    wallet_ref = Column(String(255), nullable=True)
    settlement_ref = Column(String(255), nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="PKR")
    transaction_timestamp = Column(DateTime(timezone=True), nullable=True)
    timestamp_gap_seconds = Column(Numeric(10, 2), nullable=True)
    match_confidence = Column(Numeric(5, 2), default=0.0)
    exception_reason = Column(Text, nullable=True)
    raw_data = Column(JSONB, default=dict)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)