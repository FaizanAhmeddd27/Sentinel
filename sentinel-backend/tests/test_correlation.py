import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal


@pytest.mark.asyncio
class TestCorrelationEngine:
    """
    Tests for the Correlation Engine — the most critical component.
    Stitches transaction IDs across Oracle, RAAST, Wallet, Settlement.
    """

    def _make_txn(
        self,
        txn_id: str,
        source_system: str,
        amount: float = 75000.00,
        ts_offset_seconds: int = 0,
        account_from: str = "PK36UNIL0001",
        account_to: str = "JC-9876543210",
        status: str = "created",
    ) -> dict:
        base_ts = datetime(2024, 6, 1, 9, 41, 2, tzinfo=timezone.utc)
        return {
            "id": f"raw-{txn_id}",
            "source_system": source_system,
            "source_transaction_id": txn_id,
            "amount": amount,
            "currency": "PKR",
            "account_from": account_from,
            "account_to": account_to,
            "transaction_timestamp": base_ts + timedelta(seconds=ts_offset_seconds),
            "status": status,
            "raw_data": {},
        }

    def test_engine_imports(self):
        """CorrelationEngine must be importable."""
        from app.core.correlation_engine import CorrelationEngine
        engine = CorrelationEngine()
        assert engine is not None

    def test_single_transaction_no_match(self):
        """Single transaction with no counterparts — creates lifecycle of 1."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [self._make_txn("TXN-SOLO-001", "core_banking")]
        result = engine.correlate(txns)

        assert len(result) == 1
        assert result[0]["source_count"] == 1

    def test_two_system_match_within_tolerance(self):
        """
        Oracle + RAAST transaction with same amount, account, and
        timestamp within 2-second tolerance should be correlated.
        """
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-20240601-004891", "core_banking", ts_offset_seconds=0),
            self._make_txn("RAAST-REF-88213", "raast", ts_offset_seconds=2),  # +2s = within tolerance
        ]
        result = engine.correlate(txns)

        # Should produce 1 correlated lifecycle
        assert len(result) == 1
        assert result[0]["source_count"] == 2
        identifier_map = result[0]["identifier_map"]
        assert "core_banking" in identifier_map
        assert "raast" in identifier_map

    def test_four_system_full_correlation(self):
        """
        The demo scenario: Rs. 75,000 UBL → JazzCash
        across all 4 source systems should correlate to 1 lifecycle.
        """
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-20240601-004891", "core_banking", ts_offset_seconds=0),
            self._make_txn("RAAST-REF-88213", "raast", ts_offset_seconds=2),
            self._make_txn("JC-TXN-44509", "wallet", ts_offset_seconds=12),
            self._make_txn("REV-BATCH-204-LINE-17", "settlement", ts_offset_seconds=31),
        ]
        result = engine.correlate(txns)

        assert len(result) == 1
        lifecycle = result[0]
        assert lifecycle["source_count"] == 4
        assert "core_banking" in lifecycle["identifier_map"]
        assert "raast" in lifecycle["identifier_map"]
        assert "wallet" in lifecycle["identifier_map"]
        assert "settlement" in lifecycle["identifier_map"]

    def test_different_amounts_not_correlated(self):
        """Two transactions with different amounts must NOT be correlated."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-A", "core_banking", amount=75000.00),
            self._make_txn("TXN-B", "raast", amount=50000.00),   # different amount
        ]
        result = engine.correlate(txns)

        # Should produce 2 separate lifecycles
        assert len(result) == 2

    def test_timestamp_outside_tolerance_not_correlated(self):
        """
        Transactions with same amount but timestamp gap > 2 seconds
        should NOT be auto-correlated.
        """
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-EARLY", "core_banking", ts_offset_seconds=0),
            self._make_txn("TXN-LATE", "raast", ts_offset_seconds=300),  # 5 minutes later
        ]
        result = engine.correlate(txns)

        # Should NOT correlate — too far apart
        assert len(result) == 2

    def test_retry_storm_detected(self):
        """Multiple wallet transactions for same payment should flag retry storm."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-ORACLE", "core_banking", ts_offset_seconds=0),
            self._make_txn("JC-RETRY-1", "wallet", ts_offset_seconds=12, status="retry"),
            self._make_txn("JC-RETRY-2", "wallet", ts_offset_seconds=17, status="retry"),
            self._make_txn("JC-RETRY-3", "wallet", ts_offset_seconds=22, status="retry"),
        ]
        result = engine.correlate(txns)

        # Find the lifecycle with anomalies
        lifecycle = result[0]
        anomalies = lifecycle.get("anomalies", [])
        anomaly_types = [a["type"] for a in anomalies]
        assert "retry_storm" in anomaly_types

    def test_reversal_detected(self):
        """Transaction with 'reversed' status should flag reversal anomaly."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-ORACLE", "core_banking", ts_offset_seconds=0),
            self._make_txn("RAAST-REV", "raast", ts_offset_seconds=1, status="reversed"),
        ]
        result = engine.correlate(txns)

        lifecycle = result[0]
        anomalies = lifecycle.get("anomalies", [])
        anomaly_types = [a["type"] for a in anomalies]
        assert "reversal" in anomaly_types

    def test_lifecycle_graph_structure(self):
        """Lifecycle graph must have valid nodes and edges structure."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-A", "core_banking", ts_offset_seconds=0),
            self._make_txn("TXN-B", "raast", ts_offset_seconds=2),
        ]
        result = engine.correlate(txns)
        graph = result[0]["lifecycle_graph"]

        assert "nodes" in graph
        assert "edges" in graph
        assert isinstance(graph["nodes"], list)
        assert isinstance(graph["edges"], list)
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

    def test_timeline_events_ordered(self):
        """Timeline events must be in chronological order."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        txns = [
            self._make_txn("TXN-SETTLE", "settlement", ts_offset_seconds=30),
            self._make_txn("TXN-ORACLE", "core_banking", ts_offset_seconds=0),
            self._make_txn("TXN-RAAST", "raast", ts_offset_seconds=2),
        ]
        result = engine.correlate(txns)
        events = result[0]["timeline_events"]

        assert len(events) == 3
        # First event should be core_banking (earliest timestamp)
        assert events[0]["source_system"] == "core_banking"

    def test_confidence_score_increases_with_sources(self):
        """More source systems = higher correlation confidence."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()

        # 2 systems
        txns_2 = [
            self._make_txn("TXN-A", "core_banking", ts_offset_seconds=0),
            self._make_txn("TXN-B", "raast", ts_offset_seconds=1),
        ]
        result_2 = engine.correlate(txns_2)

        # 4 systems
        txns_4 = [
            self._make_txn("TXN-C", "core_banking", ts_offset_seconds=0),
            self._make_txn("TXN-D", "raast", ts_offset_seconds=1),
            self._make_txn("TXN-E", "wallet", ts_offset_seconds=2),
            self._make_txn("TXN-F", "settlement", ts_offset_seconds=3),
        ]
        result_4 = engine.correlate(txns_4)

        confidence_2 = result_2[0]["correlation_confidence"]
        confidence_4 = result_4[0]["correlation_confidence"]
        assert confidence_4 > confidence_2

    def test_multiple_independent_payments(self):
        """Two completely separate payments should produce 2 lifecycles."""
        from app.core.correlation_engine import CorrelationEngine

        engine = CorrelationEngine()
        base = datetime(2024, 6, 1, 9, 41, 2, tzinfo=timezone.utc)

        txns = [
            # Payment 1 — Rs. 75,000
            {
                "id": "raw-1",
                "source_system": "core_banking",
                "source_transaction_id": "TXN-P1-ORACLE",
                "amount": 75000.00,
                "currency": "PKR",
                "account_from": "PK36UNIL0001",
                "account_to": "JC-9876543210",
                "transaction_timestamp": base,
                "status": "created",
                "raw_data": {},
            },
            # Payment 2 — Rs. 15,000 from different account, different time
            {
                "id": "raw-2",
                "source_system": "raast",
                "source_transaction_id": "RAAST-P2-001",
                "amount": 15000.00,
                "currency": "PKR",
                "account_from": "PK36UNIL0099",
                "account_to": "EP-1234567890",
                "transaction_timestamp": base + timedelta(hours=2),
                "status": "submitted",
                "raw_data": {},
            },
        ]

        result = engine.correlate(txns)
        assert len(result) == 2