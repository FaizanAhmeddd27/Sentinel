from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.reconciliation import ExceptionStatus


class ReconciliationBatchResponse(BaseModel):
    id: UUID
    batch_name: str
    total_records: int
    auto_matched: int
    pending_review: int
    approved: int
    dismissed: int
    status: str
    uploaded_by: UUID
    processed_at: Optional[datetime] = None
    created_at: datetime

    # Computed
    auto_match_rate: Optional[float] = None
    exceptions_requiring_review: Optional[int] = None

    model_config = {"from_attributes": True}


class ReconciliationBatchListResponse(BaseModel):
    items: List[ReconciliationBatchResponse]
    total: int
    page: int
    page_size: int


class ExceptionResponse(BaseModel):
    id: UUID
    batch_id: UUID
    exception_status: ExceptionStatus
    oracle_ref: Optional[str] = None
    raast_ref: Optional[str] = None
    wallet_ref: Optional[str] = None
    settlement_ref: Optional[str] = None
    amount: Decimal
    currency: str
    transaction_timestamp: Optional[datetime] = None
    timestamp_gap_seconds: Optional[Decimal] = None
    match_confidence: Decimal
    exception_reason: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExceptionListResponse(BaseModel):
    items: List[ExceptionResponse]
    total: int
    auto_matched_count: int
    pending_review_count: int


class ExceptionReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|dismiss)$")
    notes: Optional[str] = Field(None, max_length=1000)


class ReconciliationStatsResponse(BaseModel):
    total_processed: int
    auto_matched: int
    auto_match_rate_percent: float
    pending_review: int
    approved: int
    dismissed: int
    time_saved_hours: float
    batches_processed: int