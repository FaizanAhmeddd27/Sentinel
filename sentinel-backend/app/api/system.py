from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.celery_app import celery_app

router = APIRouter(tags=["System"])


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    """
    return {
        "status": "healthy",
        "service": "sentinel-backend",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


@router.get("/system/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    """
    Detailed system health check.

    Checks:
    - PostgreSQL
    - Redis
    - Celery Worker
    - AI Modules
    """

    status = {
        "database": "unknown",
        "redis": "unknown",
        "celery": "unknown",
        "modules": {
            "reconciliation_assistant": True,
            "incident_impact_engine": True,
            "playbook_engine": True,
            "payload_health_quarantine": True,
            "ai_incident_summary": True,
            "correlation_engine": True,
        },
    }

    # -------------------------
    # Database Health
    # -------------------------
    try:
        await db.execute(text("SELECT 1"))
        status["database"] = "healthy"
    except Exception as e:
        status["database"] = f"unhealthy: {e}"

    # -------------------------
    # Redis Health
    # -------------------------
    try:
        redis = aioredis.from_url(settings.redis_url)

        await redis.ping()

        # redis-py 5.x
        try:
            await redis.aclose()
        except AttributeError:
            # redis-py 4.x fallback
            await redis.close()

        status["redis"] = "healthy"

    except Exception as e:
        status["redis"] = f"unhealthy: {e}"

    # -------------------------
    # Celery Health
    # -------------------------
    try:
        inspector = celery_app.control.inspect(timeout=2)

        workers = inspector.ping()

        if workers:
            status["celery"] = "healthy"
            status["workers"] = list(workers.keys())
        else:
            status["celery"] = "unhealthy"

    except Exception as e:
        status["celery"] = f"unhealthy: {e}"

    # -------------------------
    # Additional Information
    # -------------------------
    status["groq_configured"] = bool(settings.groq_api_key)
    status["environment"] = settings.app_env
    status["timestamp"] = datetime.utcnow().isoformat()

    return status