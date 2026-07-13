from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys

from app.config import settings
from app.database import init_db

# Import all routers
from app.api.auth import router as auth_router
from app.api.ingestion import router as ingestion_router
from app.api.correlation import router as correlation_router
from app.api.incidents import router as incidents_router
from app.api.playbooks import router as playbooks_router
from app.api.analytics import router as analytics_router
from app.api.system import router as system_router
from app.api.users import router as users_router
from app.api.reconciliation import router as reconciliation_router
from app.api.impact import router as impact_router
from app.api.quarantine import router as quarantine_router
from app.api.ai import router as ai_router


# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.app_debug else "INFO",
)
logger.add(
    "logs/sentinel_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Sentinel Backend starting up...")
    await init_db()
    logger.info("Database initialized")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"AI Model: {settings.groq_model}")
    yield
    logger.info("Sentinel Backend shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Sentinel — Payment Operations Intelligence Platform",
    description="""
    ## Sentinel Backend API
    
    Backend for UBL Fintech Hackathon — Payment Operations Intelligence Platform.
    
    ### Features:
    - **Correlation Engine**: Stitches transaction IDs across Oracle, RAAST, Wallet, Settlement
    - **Reconciliation Assistant**: Auto-classifies 96.5% of reversal exceptions
    - **Incident Impact Engine**: Projects business impact using 90-day rolling baseline
    - **Playbook Engine**: Auto-matches operational playbooks to incidents
    - **Payload Health & Quarantine**: Intercepts malformed XML before Oracle processing
    - **AI Incident Summary**: Groq LLM-powered plain-English ops reports
    
    ### Authentication:
    Use "Continue with Google" → JWT httpOnly cookies
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Session middleware (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=3600,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(correlation_router)
app.include_router(incidents_router)
app.include_router(playbooks_router)
app.include_router(analytics_router)
app.include_router(system_router)
app.include_router(users_router)
app.include_router(reconciliation_router)
app.include_router(impact_router)
app.include_router(quarantine_router)
app.include_router(ai_router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Sentinel — Payment Operations Intelligence Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }