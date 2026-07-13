# Sentinel — Payment Operations Intelligence Platform

<div align="center">

![Sentinel](https://img.shields.io/badge/Sentinel-Payment%20Intelligence-1a3a5c?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3-FF6B35?style=for-the-badge)

**Built for UBL (United Bank Limited) Fintech Hackathon**

*Observe → Detect → Predict → Recommend → Resolve*

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Five Modules](#five-modules)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [API Keys Setup](#api-keys-setup)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Docker](#docker)
- [Database Migrations](#database-migrations)
- [Seed Data](#seed-data)
- [API Documentation](#api-documentation)
- [User Roles](#user-roles)
- [Testing](#testing)
- [Docker Hub](#docker-hub)
- [Environment Variables](#environment-variables)
- [Quick Start](#quick-start-tldr)

---

## Overview

Sentinel is a **Payment Operations Intelligence Platform** that reconstructs the complete lifecycle of every payment across Core Banking (Oracle), RAAST Gateway, Wallet APIs (JazzCash/Easypaisa), and Settlement Files.

### The Problem It Solves

| Metric | Without Sentinel | With Sentinel |
|---|---|---|
| Reconciliation (1,000 reversals) | 8 hours | 20 minutes |
| Incident investigation | 45 minutes | < 10 seconds |
| Time to first playbook action | 20+ minutes | < 60 seconds |
| Oracle batch failures from bad XML | Weekly | Near zero |
| AI incident summary | 15–30 minutes | 4 seconds |

### Key Differentiator

**Non-invasive by design.** Sentinel ingests only bank-exported files (CSV, XML, XLSX, log files). No live hooks into core banking systems. No SDK. No agent. A compliance officer can audit every data point Sentinel receives because it is the same data the bank already archives.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Ingestion Layer                      │
│  Core Banking │  RAAST Gateway │  Wallet APIs │  Settlement  │
│  (Oracle XML) │  (Session Logs)│  (CSV/JSON)  │  (T+1 CSV)   │
└──────────────────────────┬──────────────────────────────────┘
                            │ File Upload (Non-Invasive)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Celery Task Queue (Redis)                   │
│         Parse → Normalize → Store Raw Transactions           │
└──────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Correlation Engine (Core)                      │
│   rapidfuzz (fuzzy match) + networkx (graph)                 │
│   Stitches 4 source system IDs → Payment Lifecycle Graph      │
└──────────────────────────┬──────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Module 1   │  │   Module 2   │  │   Module 3   │
    │  Recon      │  │   Impact     │  │   Playbook   │
    │  Assistant  │  │   Engine     │  │   Engine     │
    └─────────────┘  └──────────────┘  └──────────────┘
           ▼                ▼
    ┌─────────────┐  ┌──────────────┐
    │  Module 4   │  │   Module 5   │
    │  Payload    │  │   AI Summary │
    │  Health &   │  │   (Groq LLM) │
    │  Quarantine │  └──────────────┘
    └─────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              Supabase (Postgres + Storage + Realtime)        │
│         FastAPI REST API  ←→  Frontend Dashboard              │
└─────────────────────────────────────────────────────────────┘
```

---

## Five Modules

### Module 1 — Reconciliation Assistant

Auto-classifies reversal exceptions using amount + timestamp + account correlation. Reduces manual review from 1,000 records to 35 per batch (96.5% auto-match rate).

**Exception taxonomy:**

| Status | Criteria | Action |
|---|---|---|
| Auto-Matched | All within tolerance | None — auto-closed |
| Pending Confirmation | Timestamp gap > 30s | Confirm settlement |
| Likely Duplicate | Same amount+account within 60s | Verify and void |
| Missing Settlement | No settlement counterpart | Escalate |
| Manual Review | Cross-currency or multi-leg | Full investigation |

### Module 2 — Incident Impact Engine

Converts raw metrics into business impact projections using a rolling 90-day baseline. Reports transactions at risk, customers affected, and PKR settlement impact at 5/10/25/60-minute windows.

### Module 3 — Operational Playbook Engine

Auto-matches incidents to operational playbooks using multi-signal scoring (incident type, keywords, source system, fuzzy title match). Each playbook contains ranked actions with expected outcomes.

### Module 4 — Payload Health & Quarantine

Pre-screens Oracle XML payloads before batch submission. Detects unescaped characters, missing required fields, and illegal control characters. Auto-generates corrected XML for human approval.

### Module 5 — AI-Assisted Incident Summary

Converts structured incident JSON to plain-English, ops-bridge-ready reports using Groq's LPU inference engine (LLaMA 3.3 70B). Factual, concise, auditable. All figures sourced from Sentinel telemetry only.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+ |
| Framework | FastAPI 0.109 |
| ASGI Server | Uvicorn + Gunicorn |
| Validation | Pydantic v2 |
| Database | Supabase (Postgres) via SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Storage | Supabase Storage |
| Auth | Google OAuth2 (Authlib) + JWT (python-jose) |
| Task Queue | Celery 5.3 + Redis 7 |
| Caching | Redis |
| Correlation | rapidfuzz + networkx |
| File Parsing | pandas + lxml + xmltodict + openpyxl |
| AI | Groq API (LLaMA 3.3 70B Versatile) |
| Logging | loguru |
| Testing | pytest + pytest-asyncio + httpx |
| Containers | Docker + Docker Compose |

---

## Project Structure

```
sentinel-backend/
├── app/
│   ├── main.py                        # FastAPI application entry point
│   ├── config.py                      # Pydantic settings (env vars)
│   ├── database.py                    # SQLAlchemy async engine + session
│   ├── celery_app.py                  # Celery configuration
│   │
│   ├── models/                        # SQLAlchemy ORM models
│   │   ├── user.py                    # User + roles
│   │   ├── ingestion.py               # Ingestion jobs
│   │   ├── transaction.py             # Raw transactions + Payment Lifecycles
│   │   ├── incident.py                # Incidents
│   │   ├── reconciliation.py          # Batches + exceptions
│   │   ├── playbook.py                # Operational playbooks
│   │   ├── quarantine.py              # Quarantined payloads
│   │   └── audit.py                   # Immutable audit trail
│   │
│   ├── schemas/                       # Pydantic v2 request/response schemas
│   │
│   ├── api/                           # FastAPI route handlers
│   │   ├── auth.py                    # Google OAuth2 + JWT
│   │   ├── users.py                   # User management (Admin)
│   │   ├── ingestion.py               # File upload + job management
│   │   ├── correlation.py             # Correlation engine triggers
│   │   ├── incidents.py               # Incident CRUD + AI summary trigger
│   │   ├── reconciliation.py          # Batch upload + exception review
│   │   ├── impact.py                  # Business impact projection
│   │   ├── playbooks.py               # Playbook CRUD + auto-match
│   │   ├── quarantine.py              # Quarantine management
│   │   ├── ai.py                      # Direct AI summarization
│   │   ├── analytics.py               # ROI + trends
│   │   └── system.py                  # Health + status
│   │
│   ├── core/                          # Business logic engines
│   │   ├── correlation_engine.py      # rapidfuzz + networkx stitching
│   │   ├── reconciliation_engine.py   # Exception classification
│   │   ├── impact_engine.py           # 90-day baseline projections
│   │   ├── playbook_matcher.py        # Multi-signal playbook scoring
│   │   ├── payload_validator.py       # XML validation + auto-correction
│   │   └── ai_summarizer.py           # Groq LLM integration
│   │
│   ├── tasks/                         # Celery async tasks
│   │   ├── ingestion_tasks.py         # File parse + DB insert
│   │   ├── correlation_tasks.py       # Correlation batch run
│   │   └── ai_tasks.py                # AI summary generation
│   │
│   ├── dependencies/                  # FastAPI dependency injection
│   │   ├── auth.py                    # JWT validation + current user
│   │   └── roles.py                   # Role-based access control
│   │
│   └── utils/
│       ├── file_parsers.py            # CSV/XML/XLSX/log parsing
│       ├── storage.py                 # Supabase Storage client
│       └── cache.py                   # Redis cache helpers
│
├── alembic/                           # Database migrations
├── tests/                             # pytest test suite
├── scripts/
│   └── seed_data.py                   # Demo data seeder
├── Dockerfile                         # FastAPI app image
├── Dockerfile.worker                  # Celery worker image
├── docker-compose.yml                 # Development compose
├── docker-compose.prod.yml            # Production compose
├── gunicorn.conf.py                   # Gunicorn production config
└── requirements.txt
```

---

## Prerequisites

- Python 3.11+
- Docker Desktop
- Git

---

## API Keys Setup

### 1. Google OAuth2

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create project → `Sentinel`
3. **APIs & Services → OAuth consent screen**
   - User Type: External
   - App name: Sentinel
   - Scopes: `email`, `profile`, `openid`
4. **APIs & Services → Credentials**
   - Create Credentials → OAuth 2.0 Client ID
   - Type: Web application
   - Authorized redirect URIs: `http://localhost:8000/auth/google/callback`
5. Copy `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

### 2. Supabase

1. Go to [supabase.com](https://supabase.com/) → New Project → `sentinel`
2. **Settings → API**:
   - Copy Project URL → `SUPABASE_URL`
   - Copy anon/public key → `SUPABASE_ANON_KEY`
   - Copy service_role key → `SUPABASE_SERVICE_KEY`
3. **Settings → Database → Connection string (URI mode)** → `DATABASE_URL`
   - Format: `postgresql+asyncpg://postgres:[password]@db.[ref].supabase.co:5432/postgres`
4. **Storage** → New bucket → `sentinel-files` (private)

### 3. Groq API

1. Go to [console.groq.com](https://console.groq.com/)
2. API Keys → Create API Key → `sentinel-production`
3. Copy `GROQ_API_KEY`
4. Free tier: 14,400 requests/day

---

## Installation

**Step 1 — Clone and create project structure**

```bash
git clone <your-repo-url>
cd sentinel-backend
```

**Step 2 — Create virtual environment**

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows
```

**Step 3 — Install dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Step 4 — Configure environment**

```bash
cp .env.example .env
# Edit .env and fill in all values
```

**Step 5 — Start Redis**

```bash
docker run -d \
  --name sentinel-redis \
  -p 6379:6379 \
  --restart unless-stopped \
  redis:7-alpine

# Verify
docker exec sentinel-redis redis-cli ping
# Expected: PONG
```

**Step 6 — Run migrations**

```bash
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
alembic current
```

**Step 7 — Seed demo data**

```bash
python scripts/seed_data.py
```

---

## Running the Application

### Local Development (3 terminals)

```bash
# Terminal 1 — Redis (if not already running)
docker start sentinel-redis

# Terminal 2 — Celery Worker
source venv/bin/activate
celery -A app.celery_app.celery_app worker \
  --loglevel=info \
  --queues=default,ingestion,correlation,ai \
  --concurrency=4

# Terminal 3 — FastAPI
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verify Running

```bash
curl http://localhost:8000/health
# {"status": "healthy", "service": "sentinel-backend"}

curl http://localhost:8000/system/status
```

### Access Points

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/health |
| Flower (Celery) | http://localhost:5555 |

---

## Docker

### Build Images

```bash
# FastAPI application
docker build -t sentinel-backend:latest -f Dockerfile .

# Celery worker
docker build -t sentinel-worker:latest -f Dockerfile.worker .
```

### Docker Compose — Development

```bash
# Build and start all services
docker-compose build
docker-compose up -d

# Check status
docker-compose ps

# Run migrations
docker-compose exec api alembic upgrade head

# Seed demo data
docker-compose exec api python scripts/seed_data.py

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Stop everything
docker-compose down

# Stop and delete all data
docker-compose down -v
```

### Docker Compose — Production

```bash
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head
docker-compose -f docker-compose.prod.yml exec api python scripts/seed_data.py
```

---

## Database Migrations

```bash
# Create new migration (after model changes)
alembic revision --autogenerate -m "description_of_change"

# Apply all pending migrations
alembic upgrade head

# Check current version
alembic current

# View history
alembic history --verbose

# Rollback one step
alembic downgrade -1

# Rollback all
alembic downgrade base
```

---

## Seed Data

The seed script creates:

- **4 users**: admin, analyst, supervisor, compliance officer
- **3 playbooks**: P-007 (RAAST), P-003 (XML), P-011 (Settlement)
- **2 incidents**: Critical RAAST timeout + High malformed payload
- **1 Payment Lifecycle**: Rs. 75,000 UBL→JazzCash (4-system correlated)
- **1 Reconciliation batch**: 1,000 records, 965 auto-matched, 35 exceptions
- **1 Quarantined payload**: Malformed Oracle XML with auto-correction

```bash
# Run seed
python scripts/seed_data.py

# Reset and re-seed
alembic downgrade base && alembic upgrade head && python scripts/seed_data.py

# Run inside Docker
docker-compose exec api python scripts/seed_data.py
```

**Demo accounts created:**

| Email | Role |
|---|---|
| admin@sentinel.ubl.pk | Admin |
| analyst@ubl.pk | Analyst |
| supervisor@ubl.pk | Supervisor |
| compliance@ubl.pk | Compliance Officer |

---

## API Documentation

FastAPI auto-generates interactive API documentation.

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Core Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| GET | `/health` | Health check | None |
| GET | `/system/status` | Module + queue status | None |
| GET | `/auth/google/login` | Google OAuth redirect | None |
| GET | `/auth/google/callback` | OAuth callback | None |
| POST | `/auth/refresh` | Refresh JWT token | Cookie |
| POST | `/auth/logout` | Clear session | JWT |
| GET | `/auth/me` | Current user info | JWT |
| POST | `/ingestion/upload` | Upload bank export file | JWT |
| GET | `/ingestion/jobs` | List ingestion jobs | JWT |
| GET | `/ingestion/audit-trail` | Compliance audit view | JWT |
| POST | `/correlation/run` | Run correlation engine | JWT |
| GET | `/correlation/graph/{txn_id}` | Payment Lifecycle Graph | JWT |
| GET | `/incidents` | List incidents (filterable) | JWT |
| GET | `/incidents/{id}` | Incident detail + AI summary | JWT |
| PATCH | `/incidents/{id}/assign` | Assign to analyst | Supervisor |
| PATCH | `/incidents/{id}/status` | Update status | JWT |
| POST | `/incidents/{id}/ai-summary` | Generate AI summary | JWT |
| GET | `/impact/{incident_id}` | Business impact projection | JWT |
| POST | `/reconciliation/upload-batch` | Upload reversal batch | JWT |
| GET | `/reconciliation/batches/{id}/exceptions` | List exceptions | JWT |
| PATCH | `/reconciliation/exceptions/{id}` | Approve/dismiss exception | JWT |
| GET | `/playbooks` | List playbooks | JWT |
| GET | `/playbooks/match/{incident_id}` | Auto-match playbook | JWT |
| POST | `/playbooks` | Create playbook | Admin/Supervisor |
| GET | `/quarantine` | List quarantined payloads | JWT |
| POST | `/quarantine/{id}/reprocess` | Reprocess payload | JWT |
| POST | `/ai/summarize` | Direct AI summarization | JWT |
| GET | `/analytics/roi` | ROI metrics | JWT |
| GET | `/analytics/trends` | Time-series trends | JWT |
| GET | `/users` | List users | Admin/Supervisor |
| PATCH | `/users/{id}/role` | Change user role | Admin |
| PATCH | `/users/{id}/status` | Activate/deactivate | Admin |

---

## User Roles

| Role | Description | Access |
|---|---|---|
| `analyst` | Front-line ops investigator | View + investigate + resolve incidents |
| `supervisor` | Team manager | Everything analyst + assign incidents + override |
| `compliance` | Auditor | Read-only audit trail + ingestion logs |
| `admin` | Full system control | User management + playbooks + all modules |

Role enforcement is implemented as FastAPI dependencies:

```python
# In any route:
from app.dependencies.auth import require_roles
from app.models.user import UserRole

@router.post("/playbooks")
async def create_playbook(
    current_user: User = Depends(
        require_roles([UserRole.admin, UserRole.supervisor])
    ),
):
    ...
```

---

## Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx aiosqlite

# Run all tests
pytest tests/ -v

# Run specific file
pytest tests/test_correlation.py -v
pytest tests/test_auth.py -v
pytest tests/test_ingestion.py -v
pytest tests/test_incidents.py -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run only unit tests (no DB/network)
pytest tests/ -v -m unit

# Run and stop on first failure
pytest tests/ -v -x
```

### Test Structure

| File | Coverage |
|---|---|
| `conftest.py` | Fixtures: DB, users, tokens, mocks |
| `test_auth.py` | Auth endpoints, JWT validation, role enforcement |
| `test_ingestion.py` | File upload, parsing (CSV/XML), payload validation |
| `test_correlation.py` | Correlation engine, 4-system stitching, anomaly detection |
| `test_incidents.py` | Impact engine, playbook matcher, reconciliation logic |

---

## Docker Hub

### Push Images

```bash
# Login
docker login

export DOCKERHUB_USERNAME=yourUsername

# Build
docker build -t ${DOCKERHUB_USERNAME}/sentinel-backend:latest -f Dockerfile .
docker build -t ${DOCKERHUB_USERNAME}/sentinel-worker:latest -f Dockerfile.worker .

# Push
docker push ${DOCKERHUB_USERNAME}/sentinel-backend:latest
docker push ${DOCKERHUB_USERNAME}/sentinel-worker:latest
```

### Pull and Deploy

```bash
export DOCKERHUB_USERNAME=yourUsername
docker pull ${DOCKERHUB_USERNAME}/sentinel-backend:latest
docker pull ${DOCKERHUB_USERNAME}/sentinel-worker:latest

DOCKERHUB_USERNAME=${DOCKERHUB_USERNAME} \
docker-compose -f docker-compose.prod.yml up -d
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | JWT signing key (min 32 chars) |
| `GOOGLE_CLIENT_ID` | ✅ | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google OAuth2 client secret |
| `GOOGLE_REDIRECT_URI` | ✅ | OAuth callback URL |
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase public anon key |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase service role key |
| `DATABASE_URL` | ✅ | Postgres connection string (asyncpg) |
| `REDIS_URL` | ✅ | Redis connection URL |
| `GROQ_API_KEY` | ✅ | Groq API key for LLM |
| `CELERY_BROKER_URL` | ✅ | Celery broker (Redis URL) |
| `CELERY_RESULT_BACKEND` | ✅ | Celery result backend (Redis URL) |
| `APP_ENV` | ❌ | `development` or `production` |
| `APP_DEBUG` | ❌ | `true` or `false` |
| `GROQ_MODEL` | ❌ | Default: `llama-3.3-70b-versatile` |
| `MAX_UPLOAD_SIZE_MB` | ❌ | Default: `50` |
| `CORRELATION_TIME_TOLERANCE_SECONDS` | ❌ | Default: `2` |
| `CORRELATION_AMOUNT_TOLERANCE_PKR` | ❌ | Default: `0.01` |

---

## Quick Start (TL;DR)

```bash
git clone <repo> && cd sentinel-backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env   # fill in API keys
docker run -d --name sentinel-redis -p 6379:6379 redis:7-alpine
alembic revision --autogenerate -m "initial_schema" && alembic upgrade head
python scripts/seed_data.py
uvicorn app.main:app --reload       # Terminal 1
celery -A app.celery_app.celery_app worker --loglevel=info  # Terminal 2
open http://localhost:8000/docs
```