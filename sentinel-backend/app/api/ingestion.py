from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.ingestion import IngestionJob, JobStatus, SourceSystem
from app.models.user import User
from app.dependencies.auth import get_current_user, require_roles
from app.models.user import UserRole
from app.config import settings
from app.utils.storage import upload_file_to_storage
from app.tasks.ingestion_tasks import process_ingestion_job
from datetime import datetime, timezone
from loguru import logger
import uuid
import os

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    source_system: SourceSystem = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a bank export file. Triggers async Celery ingestion job."""

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.allowed_file_types_list:
        raise HTTPException(
            status_code=400,
            detail=f"File type .{ext} not allowed. Allowed: {settings.allowed_file_types_list}",
        )

    # Read and validate file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f}MB. Max: {settings.max_upload_size_mb}MB",
        )

    # Upload to Supabase Storage
    storage_path = f"ingestion/{source_system.value}/{uuid.uuid4()}/{file.filename}"
    await upload_file_to_storage(content, storage_path, file.content_type)

    # Create ingestion job record
    job = IngestionJob(
        filename=file.filename,
        file_path=storage_path,
        file_size_bytes=len(content),
        source_system=source_system,
        status=JobStatus.pending,
        uploaded_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Trigger Celery task
    task = process_ingestion_job.delay(
        str(job.id), storage_path, source_system.value
    )
    job.celery_task_id = task.id
    await db.commit()

    logger.info(f"Ingestion job {job.id} created for {file.filename}")

    return {
        "job_id": str(job.id),
        "filename": file.filename,
        "source_system": source_system,
        "status": "pending",
        "celery_task_id": task.id,
        "message": "File uploaded. Processing started.",
    }


@router.get("/jobs")
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: JobStatus = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ingestion job history with pagination."""
    query = select(IngestionJob).order_by(IngestionJob.created_at.desc())

    if status:
        query = query.where(IngestionJob.status == status)

    # Compliance officers can see all, others see their own
    if current_user.role not in [UserRole.admin, UserRole.supervisor, UserRole.compliance]:
        query = query.where(IngestionJob.uploaded_by == current_user.id)

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(j.id),
                "filename": j.filename,
                "source_system": j.source_system,
                "status": j.status,
                "records_total": j.records_total,
                "records_processed": j.records_processed,
                "records_failed": j.records_failed,
                "file_size_bytes": j.file_size_bytes,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ingestion job detail with logs."""
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": str(job.id),
        "filename": job.filename,
        "source_system": job.source_system,
        "status": job.status,
        "records_total": job.records_total,
        "records_processed": job.records_processed,
        "records_failed": job.records_failed,
        "celery_task_id": job.celery_task_id,
        "error_message": job.error_message,
        "job_logs": job.job_logs,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


@router.get("/audit-trail")
async def get_audit_trail(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.compliance, UserRole.supervisor])
    ),
):
    """Compliance Officer read-only audit view of all ingestion activity."""
    query = select(IngestionJob).order_by(IngestionJob.created_at.desc())
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "audit_trail": [
            {
                "id": str(j.id),
                "filename": j.filename,
                "source_system": j.source_system,
                "status": j.status,
                "records_total": j.records_total,
                "file_size_bytes": j.file_size_bytes,
                "uploaded_by": str(j.uploaded_by),
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ],
        "total": total,
        "note": "Sentinel only ingests bank-exported files. No live transaction streams accessed.",
    }