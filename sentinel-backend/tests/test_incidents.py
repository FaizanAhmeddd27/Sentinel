import pytest
from httpx import AsyncClient
from decimal import Decimal


@pytest.mark.asyncio
class TestIncidentEndpoints:

    async def test_list_incidents_requires_auth(self, client: AsyncClient):
        """GET /incidents must require authentication."""
        response = await client.get("/incidents")
        assert response.status_code == 401

    async def test_get_incident_requires_auth(self, client: AsyncClient):
        """GET /incidents/{id} must require authentication."""
        response = await client.get(
            "/incidents/00000000-0000-0000-0000-000000000001"
        )
        assert response.status_code == 401

    async def test_incidents_filter_params_accepted(self, client: AsyncClient):
        """
        GET /incidents with filter params should not crash the server.
        Without auth we still get 401 — not 422 (validation error) or 500.
        """
        params = {
            "status": "open",
            "severity": "critical",
            "source_system": "raast",
            "page": 1,
            "page_size": 20,
        }
        response = await client.get("/incidents", params=params)
        # Without auth = 401, not 422 (params are valid) or 500 (server error)
        assert response.status_code == 401

    async def test_impact_engine_baseline_config(self):
        """Impact Engine baseline config must have all required incident types."""
        from app.core.impact_engine import BASELINE_CONFIG

        required_types = [
            "raast_timeout",
            "retry_storm",
            "wallet_degradation",
            "malformed_payload",
            "settlement_gap",
            "reversal_mismatch",
            "unknown",
        ]
        for incident_type in required_types:
            assert incident_type in BASELINE_CONFIG, (
                f"Missing baseline config for: {incident_type}"
            )
            config = BASELINE_CONFIG[incident_type]
            assert "transactions_per_minute" in config
            assert "reversal_rate_percent" in config
            assert "avg_transaction_pkr" in config
            assert "escalation_rate_per_minute" in config

    async def test_impact_engine_projection_increases_over_time(self):
        """
        Projected transaction count must increase over time
        (escalation_rate > 0).
        """
        from app.core.impact_engine import ImpactEngine, BASELINE_CONFIG

        baseline = BASELINE_CONFIG["raast_timeout"]
        engine = ImpactEngine(db=None)

        proj_5 = engine._project(baseline, elapsed=5.0, additional_minutes=5)
        proj_25 = engine._project(baseline, elapsed=5.0, additional_minutes=25)
        proj_60 = engine._project(baseline, elapsed=5.0, additional_minutes=60)

        assert proj_25 > proj_5
        assert proj_60 > proj_25

    async def test_impact_engine_severity_critical(self):
        """Transactions > 10,000 should yield CRITICAL severity."""
        from app.core.impact_engine import ImpactEngine

        engine = ImpactEngine(db=None)
        assessment = engine._assess_severity(
            projected_transactions=11200,
            settlement_impact=18_500_000.0,
        )
        assert assessment["level"] == "CRITICAL"
        assert assessment["color"] == "red"

    async def test_impact_engine_severity_medium(self):
        """Transactions 1000-5000 should yield MEDIUM severity."""
        from app.core.impact_engine import ImpactEngine

        engine = ImpactEngine(db=None)
        assessment = engine._assess_severity(
            projected_transactions=1500,
            settlement_impact=500_000.0,
        )
        assert assessment["level"] == "MEDIUM"

    async def test_playbook_matcher_imports(self):
        """PlaybookMatcher must be importable and instantiable."""
        from app.core.playbook_matcher import PlaybookMatcher
        matcher = PlaybookMatcher()
        assert matcher is not None
        assert matcher.MIN_MATCH_THRESHOLD == 30

    async def test_playbook_matcher_no_playbooks(self):
        """With empty playbook list, matcher returns None."""
        from app.core.playbook_matcher import PlaybookMatcher
        from unittest.mock import MagicMock
        from app.models.incident import IncidentType

        matcher = PlaybookMatcher()
        mock_incident = MagicMock()
        mock_incident.incident_type = IncidentType.raast_timeout
        mock_incident.title = "RAAST timeout detected"
        mock_incident.description = "Latency spike"
        mock_incident.source_system = "raast"

        result, score, signals = matcher.match(mock_incident, [])
        assert result is None
        assert score == 0
        assert signals == []

    async def test_reconciliation_engine_imports(self):
        """ReconciliationEngine must be importable."""
        from app.core.reconciliation_engine import ReconciliationEngine
        assert ReconciliationEngine is not None

    async def test_reconciliation_classification_logic(self):
        """
        ReconciliationEngine._classify must correctly classify records
        against the taxonomy.
        """
        from app.core.reconciliation_engine import ReconciliationEngine
        from app.models.reconciliation import ExceptionStatus
        from datetime import datetime, timezone

        engine = ReconciliationEngine(db=None)
        now = datetime.now(timezone.utc)

        # Case 1: Oracle ref with no settlement ref → missing_settlement
        missing_settlement_record = {
            "source_transaction_id": "TXN-ORACLE-001",
            "oracle_ref": "TXN-ORACLE-001",
            "settlement_ref": "",
            "amount": 75000.0,
            "currency": "PKR",
            "account_from": "PK36UNIL0001",
            "transaction_timestamp": now,
            "raw_data": {},
        }
        result = engine._classify(missing_settlement_record, {})
        assert result["status"] == ExceptionStatus.missing_settlement

    async def test_ai_summarizer_imports(self):
        """AISummarizer must be importable without crashing."""
        from app.core.ai_summarizer import AISummarizer
        summarizer = AISummarizer()
        assert summarizer is not None
        assert summarizer.primary_model is not None
        assert "SENTINEL INCIDENT REPORT" in AISummarizer.SYSTEM_PROMPT

    async def test_payload_validator_batch(self):
        """Validate a mixed batch of valid and invalid payloads."""
        from app.core.payload_validator import PayloadValidator

        payloads = [
            # Valid
            """<?xml version="1.0"?>
<transaction>
  <id>TXN-001</id><amount>75000</amount>
  <account>PK36UNIL0001</account>
  <timestamp>2024-06-01T09:41:02</timestamp>
</transaction>""",
            # Invalid — unescaped &
            """<?xml version="1.0"?>
<transaction>
  <id>TXN-002</id><amount>50000</amount>
  <account>PK36UNIL0002</account>
  <timestamp>2024-06-01T10:00:00</timestamp>
  <beneficiary_name>Ali & Sons</beneficiary_name>
</transaction>""",
        ]

        validator = PayloadValidator()
        result = validator.validate_batch(payloads)

        assert result["total_payloads"] == 2
        assert result["valid_payloads"] >= 1
        assert result["invalid_payloads"] >= 1
        assert result["oracle_safe_rate_percent"] < 100.0
        # Oracle processes only valid ones
        assert result["payloads_processed_cleanly"] == result["valid_payloads"]
        assert result["payloads_quarantined"] == result["invalid_payloads"]