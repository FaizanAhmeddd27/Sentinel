from app.celery_app import celery_app
from app.core.ai_summarizer import AISummarizer
from app.database import AsyncSessionLocal
from app.models.incident import Incident
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import select
import uuid


@celery_app.task(name="app.tasks.ai_tasks.generate_incident_summary", bind=True, max_retries=2)
def generate_incident_summary(self, incident_id: str):
    """Celery task: Call Groq API to generate incident summary."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Incident).where(Incident.id == uuid.UUID(incident_id))
            )
            incident = result.scalar_one_or_none()
            if not incident:
                logger.error(f"Incident {incident_id} not found for AI summary")
                return

            summarizer = AISummarizer()
            incident_data = {
                "incident_id": str(incident.id),
                "title": incident.title,
                "incident_type": incident.incident_type.value if incident.incident_type else "unknown",
                "severity": incident.severity.value if incident.severity else "medium",
                "source_system": incident.source_system,
                "transactions_affected": incident.transactions_affected,
                "customers_affected": incident.customers_affected,
                "estimated_amount_pkr": float(incident.estimated_amount_pkr or 0),
                "projected_transactions_25min": incident.projected_transactions_25min,
                "detected_at": str(incident.detected_at),
                "description": incident.description,
            }

            summary, model_used = await summarizer.generate_summary(incident_data)

            incident.ai_summary = summary
            incident.ai_summary_generated_at = datetime.now(timezone.utc)
            incident.ai_model_used = model_used
            await db.commit()

            logger.info(f"AI summary generated for incident {incident_id}")
            return summary

    result = loop.run_until_complete(_run())
    loop.close()
    return result