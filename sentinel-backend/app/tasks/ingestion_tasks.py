from app.celery_app import celery_app
from app.database import AsyncSessionLocal
from app.models.ingestion import IngestionJob, JobStatus
from app.models.transaction import RawTransaction
from app.utils.file_parsers import FileParser
from app.utils.storage import download_file_from_storage
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import select
import uuid


@celery_app.task(name="app.tasks.ingestion_tasks.process_ingestion_job", bind=True, max_retries=3)
def process_ingestion_job(self, job_id: str, file_path: str, source_system: str):
    """
    Celery task: Download file from Supabase Storage, parse it,
    insert raw records into DB, then trigger correlation.
    """
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        async with AsyncSessionLocal() as db:
            try:
                # Update job status to processing
                result = await db.execute(
                    select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id))
                )
                job = result.scalar_one_or_none()
                if not job:
                    logger.error(f"Job {job_id} not found")
                    return

                job.status = JobStatus.processing
                job.started_at = datetime.now(timezone.utc)
                await db.commit()

                logger.info(f"Processing ingestion job {job_id} for {source_system}")

                # Download file from Supabase Storage
                local_path = await download_file_from_storage(file_path)

                # Parse file
                records = FileParser.parse(local_path, source_system)
                job.records_total = len(records)
                await db.commit()

                # Insert raw transactions
                inserted = 0
                failed = 0
                for record in records:
                    try:
                        txn = RawTransaction(
                            source_system=source_system,
                            source_transaction_id=str(record.get("source_transaction_id", "")),
                            amount=record.get("amount", 0),
                            currency=record.get("currency", "PKR"),
                            account_from=str(record.get("account_from", "")) or None,
                            account_to=str(record.get("account_to", "")) or None,
                            transaction_timestamp=record.get("transaction_timestamp"),
                            status=str(record.get("status", "unknown")),
                            raw_data=record.get("raw_data", {}),
                            ingestion_job_id=uuid.UUID(job_id),
                        )
                        db.add(txn)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert record: {e}")
                        failed += 1

                await db.commit()

                job.records_processed = inserted
                job.records_failed = failed
                job.status = JobStatus.completed
                job.completed_at = datetime.now(timezone.utc)
                job.job_logs = [
                    {"timestamp": str(datetime.now(timezone.utc)),
                     "message": f"Completed: {inserted} records inserted, {failed} failed"}
                ]
                await db.commit()

                logger.info(f"Job {job_id} complete: {inserted} records")

                # Trigger correlation automatically
                from app.tasks.correlation_tasks import run_correlation
                run_correlation.delay(job_id)

            except Exception as e:
                logger.error(f"Ingestion job {job_id} failed: {e}")
                async with AsyncSessionLocal() as db2:
                    result = await db2.execute(
                        select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id))
                    )
                    job = result.scalar_one_or_none()
                    if job:
                        job.status = JobStatus.failed
                        job.error_message = str(e)
                        job.completed_at = datetime.now(timezone.utc)
                        await db2.commit()
                raise self.retry(exc=e, countdown=60)

    loop.run_until_complete(_run())
    loop.close()