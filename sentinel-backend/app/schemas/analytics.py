from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class ROIModuleStats(BaseModel):
    before_sentinel: str
    with_sentinel: str
    improvement: Optional[str] = None


class ReconciliationROI(BaseModel):
    total_records_processed: int
    auto_matched: int
    auto_match_rate_percent: float
    manual_reviews_required: int
    time_saved_hours: float
    before_sentinel: str
    with_sentinel: str


class IncidentROI(BaseModel):
    total_incidents: int
    ai_summaries_generated: int
    investigation_time_before: str
    investigation_time_after: str
    time_saved_per_incident_minutes: int


class PayloadHealthROI(BaseModel):
    oracle_outages_prevented: str
    malformed_payloads_caught: int
    oracle_batch_failure_impact: str


class PlaybookROI(BaseModel):
    time_to_first_action_before: str
    time_to_first_action_after: str


class ROISummary(BaseModel):
    overall_time_saved_hours: float
    incidents_managed: int
    incidents_resolved: int


class ROIResponse(BaseModel):
    summary: ROISummary
    reconciliation: ReconciliationROI
    incident_management: IncidentROI
    payload_health: PayloadHealthROI
    playbook_engine: PlaybookROI


class TrendDataPoint(BaseModel):
    date: str
    incident_count: int
    resolved_count: int
    resolution_rate: float


class TrendsResponse(BaseModel):
    period: str
    days: int
    data: List[TrendDataPoint]