from app.celery_app import celery_app
from app.database import AsyncSessionLocal
from app.models.transaction import RawTransaction, PaymentLifecycle
from app.models.ingestion import IngestionJob
from app.core.correlation_engine import CorrelationEngine
from app.core.impact_engine import ImpactEngine
from app.models.incident import Incident, IncidentType, IncidentSeverity, IncidentStatus
from sqlalchemy import select
from datetime import datetime, timezone
from decimal import Decimal
from loguru import logger
import uuid
import asyncio


@celery_app.task(
    name="app.tasks.correlation_tasks.run_correlation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_correlation(self, job_id: str = None):
    """
    Celery task: Run the Correlation Engine on raw transactions.

    Steps:
    1. Fetch unprocessed raw transactions (optionally filtered by job_id)
    2. Run CorrelationEngine to stitch identifiers across source systems
    3. Persist PaymentLifecycle objects to DB
    4. Detect anomalies → create Incident records
    5. Trigger AI summary for critical incidents
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        async with AsyncSessionLocal() as db:
            logger.info(f"Correlation task started (job_id={job_id})")

            # Fetch raw transactions not yet correlated
            query = select(RawTransaction).where(
                RawTransaction.correlation_group_id.is_(None)
            )
            if job_id:
                query = query.where(
                    RawTransaction.ingestion_job_id == uuid.UUID(job_id)
                )
            query = query.limit(5000)  # Process in chunks

            result = await db.execute(query)
            raw_transactions = result.scalars().all()

            if not raw_transactions:
                logger.info("No uncorrelated transactions found")
                return {"correlated": 0, "incidents_created": 0}

            logger.info(f"Correlating {len(raw_transactions)} raw transactions")

            # Serialize to dicts for the engine
            txn_dicts = [
                {
                    "id": str(t.id),
                    "source_system": t.source_system,
                    "source_transaction_id": t.source_transaction_id,
                    "amount": float(t.amount or 0),
                    "currency": t.currency or "PKR",
                    "account_from": t.account_from,
                    "account_to": t.account_to,
                    "transaction_timestamp": t.transaction_timestamp,
                    "status": t.status or "unknown",
                    "raw_data": t.raw_data or {},
                }
                for t in raw_transactions
            ]

            # Run correlation engine
            engine = CorrelationEngine()
            lifecycles = engine.correlate(txn_dicts)

            logger.info(f"Correlation complete: {len(lifecycles)} payment lifecycles")

            # Persist lifecycles and update raw transactions
            incidents_created = 0
            lifecycle_id_map = {}  # canonical_id → db UUID

            for lc_data in lifecycles:
                lifecycle = PaymentLifecycle(
                    canonical_id=lc_data["canonical_id"],
                    amount=Decimal(str(lc_data.get("amount", 0))),
                    currency=lc_data.get("currency", "PKR"),
                    account_from=lc_data.get("account_from"),
                    account_to=lc_data.get("account_to"),
                    initiated_at=_parse_ts(lc_data.get("initiated_at")),
                    status=lc_data.get("status", "pending_reconciliation"),
                    identifier_map=lc_data.get("identifier_map", {}),
                    lifecycle_graph=lc_data.get("lifecycle_graph", {}),
                    timeline_events=lc_data.get("timeline_events", []),
                    correlation_confidence=Decimal(
                        str(lc_data.get("correlation_confidence", 0))
                    ),
                    source_count=str(lc_data.get("source_count", 1)),
                )
                db.add(lifecycle)
                await db.flush()  # Get the ID

                lifecycle_id_map[lc_data["canonical_id"]] = lifecycle.id

                # Mark raw transactions as correlated
                for txn_id_str in lc_data.get("source_transactions", []):
                    try:
                        txn_result = await db.execute(
                            select(RawTransaction).where(
                                RawTransaction.id == uuid.UUID(txn_id_str)
                            )
                        )
                        txn = txn_result.scalar_one_or_none()
                        if txn:
                            txn.correlation_group_id = lifecycle.id
                    except Exception:
                        pass

                # Create incidents from anomalies
                anomalies = lc_data.get("anomalies", [])
                for anomaly in anomalies:
                    incident = _build_incident(anomaly, lifecycle)
                    if incident:
                        db.add(incident)
                        incidents_created += 1

            await db.commit()
            logger.info(
                f"Correlation persisted: {len(lifecycles)} lifecycles, "
                f"{incidents_created} incidents created"
            )

            # Trigger AI summaries for critical incidents (async)
            if incidents_created > 0:
                from app.tasks.ai_tasks import generate_incident_summary
                result2 = await db.execute(
                    select(Incident)
                    .where(Incident.severity == IncidentSeverity.critical)
                    .where(Incident.ai_summary.is_(None))
                    .limit(10)
                )
                critical_incidents = result2.scalars().all()
                for inc in critical_incidents:
                    generate_incident_summary.delay(str(inc.id))

            return {
                "correlated": len(lifecycles),
                "incidents_created": incidents_created,
                "raw_transactions_processed": len(raw_transactions),
            }

    try:
        result = loop.run_until_complete(_run())
        loop.close()
        return result
    except Exception as e:
        loop.close()
        logger.error(f"Correlation task failed: {e}")
        raise self.retry(exc=e)


def _parse_ts(ts_str):
    """Safely parse timestamp string."""
    if not ts_str:
        return None
    if isinstance(ts_str, datetime):
        return ts_str
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        return None


def _build_incident(anomaly: dict, lifecycle: PaymentLifecycle):
    """Build an Incident from a detected anomaly."""
    anomaly_type = anomaly.get("type", "unknown")
    severity_map = {
        "high": IncidentSeverity.high,
        "medium": IncidentSeverity.medium,
        "low": IncidentSeverity.low,
        "critical": IncidentSeverity.critical,
    }
    type_map = {
        "retry_storm": IncidentType.retry_storm,
        "reversal": IncidentType.reversal_mismatch,
        "latency_gap": IncidentType.raast_timeout,
        "duplicate": IncidentType.duplicate_transaction,
    }

    return Incident(
        title=f"{anomaly.get('description', 'Anomaly detected')} — {lifecycle.canonical_id}",
        description=anomaly.get("description"),
        incident_type=type_map.get(anomaly_type, IncidentType.unknown),
        severity=severity_map.get(anomaly.get("severity", "medium"), IncidentSeverity.medium),
        status=IncidentStatus.open,
        source_system=lifecycle.identifier_map.get("raast") and "raast" or "core_banking",
        payment_lifecycle_id=lifecycle.id,
        transactions_affected=anomaly.get("count", 1),
        estimated_amount_pkr=lifecycle.amount or Decimal("0"),
        raw_incident_data={
            "anomaly": anomaly,
            "lifecycle_canonical_id": lifecycle.canonical_id,
            "identifier_map": lifecycle.identifier_map,
        },
        detected_at=datetime.now(timezone.utc),
    )