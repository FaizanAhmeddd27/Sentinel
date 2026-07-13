"""
Seed the database with realistic demo data for the hackathon demo.
Creates the full disaster scenario: Rs. 75,000 UBL → JazzCash payment.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.models.user import User, UserRole, UserStatus
from app.models.incident import Incident, IncidentSeverity, IncidentStatus, IncidentType
from app.models.transaction import RawTransaction, PaymentLifecycle
from app.models.reconciliation import ReconciliationBatch, ReconciliationException, ExceptionStatus
from app.models.playbook import Playbook
from app.models.quarantine import QuarantinedPayload, QuarantineStatus
from datetime import datetime, timezone
from decimal import Decimal
import uuid


DEMO_SCENARIO_TIME = datetime(2024, 6, 1, 9, 41, 2, tzinfo=timezone.utc)


async def seed():
    async with AsyncSessionLocal() as db:
        print("🌱 Seeding Sentinel demo data...")

        # 1. Create users
        admin = User(
            email="admin@sentinel.ubl.pk",
            full_name="Sentinel Admin",
            role=UserRole.admin,
            status=UserStatus.active,
            is_first_login=False,
        )
        analyst = User(
            email="analyst@ubl.pk",
            full_name="Ops Analyst - Karachi",
            role=UserRole.analyst,
            status=UserStatus.active,
            is_first_login=False,
        )
        supervisor = User(
            email="supervisor@ubl.pk",
            full_name="Ops Supervisor",
            role=UserRole.supervisor,
            status=UserStatus.active,
            is_first_login=False,
        )
        compliance = User(
            email="compliance@ubl.pk",
            full_name="Compliance Officer",
            role=UserRole.compliance,
            status=UserStatus.active,
            is_first_login=False,
        )
        db.add_all([admin, analyst, supervisor, compliance])
        await db.commit()
        print("✅ Users created")

        # 2. Create playbooks
        playbook_raast = Playbook(
            playbook_code="P-007",
            title="RAAST Gateway Timeout — Retry Storm Response",
            description="Triggered when RAAST latency exceeds 800ms threshold causing wallet retry storms",
            trigger_incident_types=["raast_timeout", "retry_storm"],
            trigger_keywords=["raast", "timeout", "latency", "retry", "wallet"],
            root_cause_hypothesis="JazzCash endpoint timeout caused by RAAST degradation",
            confidence_score=87,
            actions=[
                {
                    "step": 1,
                    "type": "immediate",
                    "action": "Increase retry interval from 5s to 15s",
                    "expected_outcome": "45% reduction in DB load within 8 minutes",
                    "command": "UPDATE payment_config SET retry_interval=15 WHERE provider='jazzcash'",
                },
                {
                    "step": 2,
                    "type": "short_term",
                    "action": "Activate queue diversion to secondary wallet provider",
                    "expected_outcome": "60% of affected transactions rerouted",
                },
                {
                    "step": 3,
                    "type": "escalation",
                    "action": "Trigger SLA notification to JazzCash operations",
                    "expected_outcome": "Formal SLA clock started",
                    "contact": "jazzcash-ops@jazzcash.com.pk",
                },
            ],
            monitor_metrics=["raast_queue_depth", "oracle_batch_position", "wallet_retry_rate"],
            estimated_resolution_minutes=25,
            is_active=1,
            created_by=admin.id,
            usage_count=47,
        )

        playbook_xml = Playbook(
            playbook_code="P-003",
            title="Malformed XML Payload — Oracle Batch Pre-screening",
            description="Intercept malformed Oracle XML payloads before batch processing",
            trigger_incident_types=["malformed_payload"],
            trigger_keywords=["xml", "malformed", "payload", "oracle", "character", "batch"],
            root_cause_hypothesis="Special character in beneficiary name field (confidence: 94%)",
            confidence_score=94,
            actions=[
                {
                    "step": 1,
                    "type": "immediate",
                    "action": "Move affected payloads to quarantine queue",
                    "expected_outcome": "Oracle processes remaining valid payloads cleanly",
                },
                {
                    "step": 2,
                    "type": "immediate",
                    "action": "Generate corrected XML with escaped special characters",
                    "expected_outcome": "Corrected batch ready for human approval",
                },
                {
                    "step": 3,
                    "type": "short_term",
                    "action": "Enable pre-submission character validation on source endpoint",
                    "expected_outcome": "Prevented Oracle batch failure affecting ~4,000 transactions",
                },
            ],
            monitor_metrics=["oracle_batch_status", "quarantine_queue_depth"],
            estimated_resolution_minutes=15,
            is_active=1,
            created_by=admin.id,
            usage_count=23,
        )

        playbook_settlement = Playbook(
            playbook_code="P-011",
            title="Missing Settlement — Reversal Reconciliation",
            description="Handle Oracle reversals with no settlement counterpart",
            trigger_incident_types=["reversal_mismatch", "settlement_gap"],
            trigger_keywords=["reversal", "settlement", "missing", "batch", "reconciliation"],
            root_cause_hypothesis="T+1 settlement batch did not include reversal leg",
            confidence_score=78,
            actions=[
                {
                    "step": 1,
                    "type": "immediate",
                    "action": "Flag for missing settlement in reconciliation dashboard",
                    "expected_outcome": "Settlement team notified within 5 minutes",
                },
                {
                    "step": 2,
                    "type": "short_term",
                    "action": "Escalate to settlement team for manual matching",
                    "expected_outcome": "Settlement leg identified and matched",
                },
            ],
            monitor_metrics=["settlement_batch_status", "open_reversal_count"],
            estimated_resolution_minutes=60,
            is_active=1,
            created_by=admin.id,
            usage_count=89,
        )
        db.add_all([playbook_raast, playbook_xml, playbook_settlement])
        await db.commit()
        print("✅ Playbooks created (P-007, P-003, P-011)")

        # 3. Create the demo disaster incident
        incident_raast = Incident(
            title="RAAST Gateway Timeout → Retry Storm → 850 Transactions Affected",
            description="RAAST processing latency increased 175% above baseline at 09:41, triggering a retry storm across active wallet transactions. Reversal volume projected at 370 transactions within 25 minutes.",
            incident_type=IncidentType.raast_timeout,
            severity=IncidentSeverity.critical,
            status=IncidentStatus.open,
            source_system="raast",
            transactions_affected=850,
            customers_affected=412,
            estimated_amount_pkr=Decimal("18500000.00"),
            projected_transactions_25min=11200,
            recommended_playbook_id=playbook_raast.id,
            ai_summary="""SENTINEL INCIDENT REPORT — Auto-generated 09:42:18

RAAST processing latency increased 175% above baseline at 09:41 and triggered a retry storm across 850 active wallet transactions. Three successive retry attempts at 5-second intervals were recorded before automatic reversal at 09:41:32.

Reversal volume is projected to reach 370 transactions within 25 minutes if latency is not resolved. Estimated settlement impact: Rs. 18.5M across 412 affected customers.

Immediate action required: Reduce retry interval from 5s to 15s to reduce DB load by 45%. Activate secondary wallet routing. Playbook P-007 has been pre-loaded. All figures sourced from Sentinel telemetry — not inferred.""",
            ai_summary_generated_at=datetime(2024, 6, 1, 9, 42, 18, tzinfo=timezone.utc),
            ai_model_used="llama-3.3-70b-versatile",
            detected_at=datetime(2024, 6, 1, 9, 41, 34, tzinfo=timezone.utc),
        )

        incident_xml = Incident(
            title="87 Malformed XML Payloads — Oracle Batch Pre-screened",
            description="Special characters detected in beneficiary name fields across 87 payloads queued for Oracle processing. Quarantined before batch execution.",
            incident_type=IncidentType.malformed_payload,
            severity=IncidentSeverity.high,
            status=IncidentStatus.in_progress,
            source_system="core_banking",
            transactions_affected=87,
            customers_affected=87,
            estimated_amount_pkr=Decimal("4500000.00"),
            recommended_playbook_id=playbook_xml.id,
            detected_at=datetime(2024, 6, 1, 8, 15, 0, tzinfo=timezone.utc),
        )
        db.add_all([incident_raast, incident_xml])
        await db.commit()
        print("✅ Demo incidents created")

        # 4. Create Payment Lifecycle (correlated from 4 systems)
        lifecycle = PaymentLifecycle(
            canonical_id="PLO-75K-DEMO",
            amount=Decimal("75000.00"),
            currency="PKR",
            account_from="PK36UNIL0000000000001234",
            account_to="JC-WALLET-9876543210",
            initiated_at=DEMO_SCENARIO_TIME,
            status="reversed",
            identifier_map={
                "core_banking": "TXN-20240601-004891",
                "raast": "RAAST-REF-88213",
                "wallet": "JC-TXN-44509",
                "settlement": "REV-BATCH-204-LINE-17",
            },
            lifecycle_graph={
                "nodes": [
                    {"id": "TXN-20240601-004891", "source_system": "core_banking",
                     "timestamp": "2024-06-01T09:41:02", "status": "created", "amount": "75000"},
                    {"id": "RAAST-REF-88213", "source_system": "raast",
                     "timestamp": "2024-06-01T09:41:04", "status": "submitted", "amount": "75000"},
                    {"id": "JC-TXN-44509", "source_system": "wallet",
                     "timestamp": "2024-06-01T09:41:14", "status": "retry_storm", "amount": "75000"},
                    {"id": "REV-BATCH-204-LINE-17", "source_system": "settlement",
                     "timestamp": "2024-06-01T09:41:33", "status": "reversal_matched", "amount": "75000"},
                ],
                "edges": [
                    {"source": "TXN-20240601-004891", "target": "RAAST-REF-88213", "relationship": "follows"},
                    {"source": "RAAST-REF-88213", "target": "JC-TXN-44509", "relationship": "follows"},
                    {"source": "JC-TXN-44509", "target": "REV-BATCH-204-LINE-17", "relationship": "follows"},
                ],
            },
            timeline_events=[
                {"timestamp": "2024-06-01T09:41:02", "source_system": "core_banking",
                 "transaction_id": "TXN-20240601-004891", "status": "created",
                 "event": "Created in Core Banking (Oracle)"},
                {"timestamp": "2024-06-01T09:41:04", "source_system": "raast",
                 "transaction_id": "RAAST-REF-88213", "status": "submitted",
                 "event": "Submitted to RAAST Gateway"},
                {"timestamp": "2024-06-01T09:41:09", "source_system": "raast",
                 "transaction_id": "RAAST-REF-88213", "status": "latency_anomaly",
                 "event": "⚠ RAAST latency: 2,200ms (threshold: 800ms) — ANOMALY DETECTED"},
                {"timestamp": "2024-06-01T09:41:14", "source_system": "wallet",
                 "transaction_id": "JC-TXN-44509", "status": "retry",
                 "event": "Wallet retry #1 → #2 → #3 (5s intervals)"},
                {"timestamp": "2024-06-01T09:41:32", "source_system": "raast",
                 "transaction_id": "RAAST-REF-88213", "status": "reversed",
                 "event": "Transaction reversed by RAAST — REV-001"},
                {"timestamp": "2024-06-01T09:41:33", "source_system": "settlement",
                 "transaction_id": "REV-BATCH-204-LINE-17", "status": "reconciliation_exception",
                 "event": "Reconciliation exception raised — Settlement batch #204 line 17"},
                {"timestamp": "2024-06-01T09:41:34", "source_system": "sentinel",
                 "transaction_id": "PLO-75K-DEMO", "status": "auto_classified",
                 "event": "✅ Sentinel: RAAST Timeout → Retry Storm → Reversal — Playbook P-007 loaded"},
            ],
            correlation_confidence=Decimal("97.5"),
            source_count=4,
        )
        db.add(lifecycle)

        # Update incident with lifecycle
        incident_raast.payment_lifecycle_id = lifecycle.id
        await db.commit()
        print("✅ Payment Lifecycle Graph created (4-system correlation)")

        # 5. Create Reconciliation Batch
        batch = ReconciliationBatch(
            batch_name="Settlement Batch #204 — 2024-06-01",
            total_records=1000,
            auto_matched=965,
            pending_review=35,
            approved=0,
            dismissed=0,
            status="completed",
            uploaded_by=analyst.id,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(batch)
        await db.commit()

        # Create sample exceptions
        exceptions = [
            ReconciliationException(
                batch_id=batch.id,
                exception_status=ExceptionStatus.missing_settlement,
                oracle_ref="TXN-20240601-004891",
                raast_ref="RAAST-REF-88213",
                wallet_ref="JC-TXN-44509",
                settlement_ref=None,
                amount=Decimal("75000.00"),
                currency="PKR",
                transaction_timestamp=DEMO_SCENARIO_TIME,
                timestamp_gap_seconds=Decimal("31.0"),
                match_confidence=Decimal("43.0"),
                exception_reason="Oracle reversal with no settlement counterpart found within tolerance window",
            ),
            ReconciliationException(
                batch_id=batch.id,
                exception_status=ExceptionStatus.likely_duplicate,
                oracle_ref="TXN-20240601-004892",
                amount=Decimal("15000.00"),
                currency="PKR",
                transaction_timestamp=DEMO_SCENARIO_TIME,
                timestamp_gap_seconds=Decimal("4.0"),
                match_confidence=Decimal("67.0"),
                exception_reason="Same amount + account, two entries within 60s",
            ),
            ReconciliationException(
                batch_id=batch.id,
                exception_status=ExceptionStatus.pending_confirmation,
                oracle_ref="TXN-20240601-004900",
                settlement_ref="REV-BATCH-204-LINE-44",
                amount=Decimal("250000.00"),
                currency="PKR",
                transaction_timestamp=DEMO_SCENARIO_TIME,
                timestamp_gap_seconds=Decimal("45.0"),
                match_confidence=Decimal("81.0"),
                exception_reason="Amount matches, timestamp gap > 30s",
            ),
        ]
        db.add_all(exceptions)
        await db.commit()
        print("✅ Reconciliation batch + 35 exceptions created (965 auto-matched)")

        # 6. Create quarantined payloads
        quarantine1 = QuarantinedPayload(
            source_system="core_banking",
            original_filename="oracle_batch_20240601.xml",
            raw_payload="""<?xml version="1.0" encoding="UTF-8"?>
<transaction>
  <id>TXN-20240601-004950</id>
  <amount>50000.00</amount>
  <beneficiary_name>محمد علی & Sons <Co></beneficiary_name>
  <account>PK36UNIL0000000000009999</account>
  <timestamp>2024-06-01T10:15:00</timestamp>
</transaction>""",
            corrected_payload="""<?xml version="1.0" encoding="UTF-8"?>
<transaction>
  <id>TXN-20240601-004950</id>
  <amount>50000.00</amount>
  <beneficiary_name>محمد علی &amp; Sons &lt;Co&gt;</beneficiary_name>
  <account>PK36UNIL0000000000009999</account>
  <timestamp>2024-06-01T10:15:00</timestamp>
</transaction>""",
            validation_errors=[
                {"field": "beneficiary_name", "error": "Unescaped special character '&'", "value": "محمد علی & Sons <Co>"},
                {"field": "beneficiary_name", "error": "Unescaped special character '<'", "value": "محمد علی & Sons <Co>"},
            ],
            error_count=2,
            status=QuarantineStatus.quarantined,
            incident_id=incident_xml.id,
        )
        db.add(quarantine1)
        await db.commit()
        print("✅ Quarantined payloads created")

        print("\n" + "="*60)
        print("✅ SEED COMPLETE — Demo data ready")
        print("="*60)
        print(f"Admin:      admin@sentinel.ubl.pk")
        print(f"Analyst:    analyst@ubl.pk")
        print(f"Supervisor: supervisor@ubl.pk")
        print(f"Compliance: compliance@ubl.pk")
        print(f"\nDemo incident: 'RAAST Gateway Timeout' (Critical)")
        print(f"Demo lifecycle: PLO-75K-DEMO (4-system correlation)")
        print(f"Reconciliation: 1000 records, 965 auto-matched, 35 exceptions")
        print(f"Playbooks: P-007 (RAAST), P-003 (XML), P-011 (Settlement)")


if __name__ == "__main__":
    asyncio.run(seed())