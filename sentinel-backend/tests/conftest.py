import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import uuid

# ── App imports ───────────────────────────────────────────────────────────────
from app.main import app
from app.database import get_db, Base
from app.config import settings
from app.models.user import User, UserRole, UserStatus
from app.models.incident import (
    Incident,
    IncidentType,
    IncidentSeverity,
    IncidentStatus,
)
from app.models.playbook import Playbook
from app.models.reconciliation import ReconciliationBatch, ReconciliationException, ExceptionStatus
from app.models.quarantine import QuarantinedPayload, QuarantineStatus
from app.models.ingestion import IngestionJob, JobStatus, SourceSystem
from app.models.transaction import PaymentLifecycle

# ── Test database URL (SQLite in-memory for tests) ───────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_sentinel.db"


# ════════════════════════════════════════════════════════════════════════════
# EVENT LOOP
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create a single event loop for the entire test session.
    Required for session-scoped async fixtures.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ════════════════════════════════════════════════════════════════════════════
# DATABASE ENGINE & SESSION
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
async def test_engine():
    """
    Create a test SQLite engine for the entire session.
    SQLite with StaticPool for in-memory testing without connection reuse issues.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="session")
async def test_session_factory(test_engine):
    """Session factory bound to the test engine."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest.fixture(scope="function")
async def db_session(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database session for each test function.
    Rolls back after each test to ensure isolation.
    """
    async with test_session_factory() as session:
        yield session
        await session.rollback()


# ════════════════════════════════════════════════════════════════════════════
# OVERRIDE FASTAPI DEPENDENCIES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client with database dependency overridden
    to use the test SQLite session.
    """

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════════════════
# JWT TOKEN HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _make_token(user_id: str, role: str, expired: bool = False) -> str:
    """Generate a test JWT token."""
    from jose import jwt

    if expired:
        exp = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        exp = datetime.now(timezone.utc) + timedelta(hours=2)

    payload = {
        "sub": user_id,
        "role": role,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _make_refresh_token(user_id: str) -> str:
    """Generate a test refresh JWT token."""
    from jose import jwt

    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# ════════════════════════════════════════════════════════════════════════════
# USER FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> User:
    """Create and return a test admin user."""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@sentinel-test.com",
        full_name="Test Admin",
        google_id="google_admin_123",
        role=UserRole.admin,
        status=UserStatus.active,
        is_first_login=False,
        last_login=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def analyst_user(db_session: AsyncSession) -> User:
    """Create and return a test analyst user."""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        email="analyst@sentinel-test.com",
        full_name="Test Analyst",
        google_id="google_analyst_456",
        role=UserRole.analyst,
        status=UserStatus.active,
        is_first_login=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def supervisor_user(db_session: AsyncSession) -> User:
    """Create and return a test supervisor user."""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        email="supervisor@sentinel-test.com",
        full_name="Test Supervisor",
        google_id="google_supervisor_789",
        role=UserRole.supervisor,
        status=UserStatus.active,
        is_first_login=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def compliance_user(db_session: AsyncSession) -> User:
    """Create and return a test compliance officer user."""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        email="compliance@sentinel-test.com",
        full_name="Test Compliance Officer",
        google_id="google_compliance_000",
        role=UserRole.compliance,
        status=UserStatus.active,
        is_first_login=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def inactive_user(db_session: AsyncSession) -> User:
    """Create and return an inactive user (deactivated account)."""
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000005"),
        email="inactive@sentinel-test.com",
        full_name="Inactive User",
        google_id="google_inactive_999",
        role=UserRole.analyst,
        status=UserStatus.inactive,
        is_first_login=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ════════════════════════════════════════════════════════════════════════════
# AUTH TOKEN FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def admin_token(admin_user: User) -> str:
    """JWT token for admin user."""
    return _make_token(str(admin_user.id), "admin")


@pytest.fixture(scope="function")
def analyst_token(analyst_user: User) -> str:
    """JWT token for analyst user."""
    return _make_token(str(analyst_user.id), "analyst")


@pytest.fixture(scope="function")
def supervisor_token(supervisor_user: User) -> str:
    """JWT token for supervisor user."""
    return _make_token(str(supervisor_user.id), "supervisor")


@pytest.fixture(scope="function")
def compliance_token(compliance_user: User) -> str:
    """JWT token for compliance officer user."""
    return _make_token(str(compliance_user.id), "compliance")


@pytest.fixture(scope="function")
def expired_token(analyst_user: User) -> str:
    """Expired JWT token for testing auth failures."""
    return _make_token(str(analyst_user.id), "analyst", expired=True)


@pytest.fixture(scope="function")
def admin_headers(admin_token: str) -> dict:
    """Auth headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def analyst_headers(analyst_token: str) -> dict:
    """Auth headers for analyst user."""
    return {"Authorization": f"Bearer {analyst_token}"}


@pytest.fixture(scope="function")
def supervisor_headers(supervisor_token: str) -> dict:
    """Auth headers for supervisor user."""
    return {"Authorization": f"Bearer {supervisor_token}"}


@pytest.fixture(scope="function")
def compliance_headers(compliance_token: str) -> dict:
    """Auth headers for compliance officer."""
    return {"Authorization": f"Bearer {compliance_token}"}


# ════════════════════════════════════════════════════════════════════════════
# INCIDENT FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_incident(
    db_session: AsyncSession,
    analyst_user: User,
) -> Incident:
    """Create and return a sample open incident."""
    from decimal import Decimal

    incident = Incident(
        id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        title="RAAST Gateway Timeout — Test Incident",
        description="RAAST latency spiked 175% above baseline",
        incident_type=IncidentType.raast_timeout,
        severity=IncidentSeverity.critical,
        status=IncidentStatus.open,
        source_system="raast",
        transactions_affected=850,
        customers_affected=412,
        estimated_amount_pkr=Decimal("18500000.00"),
        projected_transactions_25min=11200,
        detected_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(incident)
    await db_session.commit()
    await db_session.refresh(incident)
    return incident


@pytest.fixture(scope="function")
async def resolved_incident(
    db_session: AsyncSession,
    analyst_user: User,
) -> Incident:
    """Create and return a resolved incident."""
    from decimal import Decimal

    incident = Incident(
        id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
        title="Malformed XML Payload — Resolved",
        description="87 malformed payloads quarantined and reprocessed",
        incident_type=IncidentType.malformed_payload,
        severity=IncidentSeverity.high,
        status=IncidentStatus.resolved,
        source_system="core_banking",
        transactions_affected=87,
        customers_affected=87,
        estimated_amount_pkr=Decimal("4500000.00"),
        ai_summary="SENTINEL INCIDENT REPORT — Test summary. All resolved.",
        ai_summary_generated_at=datetime.now(timezone.utc),
        ai_model_used="llama-3.3-70b-versatile",
        resolved_by=analyst_user.id,
        resolved_at=datetime.now(timezone.utc),
        detected_at=datetime.now(timezone.utc) - timedelta(hours=2),
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(incident)
    await db_session.commit()
    await db_session.refresh(incident)
    return incident


@pytest.fixture(scope="function")
async def multiple_incidents(
    db_session: AsyncSession,
) -> list[Incident]:
    """Create multiple incidents for list/filter testing."""
    from decimal import Decimal

    incidents = [
        Incident(
            title=f"Test Incident {i}",
            incident_type=IncidentType.raast_timeout,
            severity=IncidentSeverity.high,
            status=IncidentStatus.open,
            source_system="raast",
            transactions_affected=100 * i,
            customers_affected=50 * i,
            estimated_amount_pkr=Decimal(str(1000000 * i)),
            detected_at=datetime.now(timezone.utc) - timedelta(hours=i),
            created_at=datetime.now(timezone.utc) - timedelta(hours=i),
        )
        for i in range(1, 6)
    ]
    db_session.add_all(incidents)
    await db_session.commit()
    return incidents


# ════════════════════════════════════════════════════════════════════════════
# PLAYBOOK FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_playbook(
    db_session: AsyncSession,
    admin_user: User,
) -> Playbook:
    """Create and return a sample playbook."""
    playbook = Playbook(
        id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
        playbook_code="P-007",
        title="RAAST Gateway Timeout — Retry Storm Response",
        description="Triggered when RAAST latency exceeds 800ms",
        trigger_incident_types=["raast_timeout", "retry_storm"],
        trigger_keywords=["raast", "timeout", "latency", "retry"],
        root_cause_hypothesis="JazzCash endpoint timeout",
        confidence_score=87,
        actions=[
            {
                "step": 1,
                "type": "immediate",
                "action": "Increase retry interval from 5s to 15s",
                "expected_outcome": "45% reduction in DB load",
            },
            {
                "step": 2,
                "type": "short_term",
                "action": "Activate queue diversion to secondary wallet",
                "expected_outcome": "60% transactions rerouted",
            },
        ],
        monitor_metrics=["raast_queue_depth", "oracle_batch_position"],
        estimated_resolution_minutes=25,
        is_active=True,
        usage_count=47,
        created_by=admin_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    return playbook


@pytest.fixture(scope="function")
async def multiple_playbooks(
    db_session: AsyncSession,
    admin_user: User,
) -> list[Playbook]:
    """Create multiple playbooks for list testing."""
    playbooks = [
        Playbook(
            playbook_code=f"P-{str(i).zfill(3)}",
            title=f"Test Playbook {i}",
            trigger_incident_types=["raast_timeout"],
            trigger_keywords=["raast", "test"],
            actions=[],
            is_active=True,
            usage_count=i * 5,
            created_by=admin_user.id,
            created_at=datetime.now(timezone.utc),
        )
        for i in range(1, 4)
    ]
    db_session.add_all(playbooks)
    await db_session.commit()
    return playbooks


# ════════════════════════════════════════════════════════════════════════════
# RECONCILIATION FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_batch(
    db_session: AsyncSession,
    analyst_user: User,
) -> ReconciliationBatch:
    """Create and return a sample reconciliation batch."""
    batch = ReconciliationBatch(
        id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
        batch_name="Settlement Batch #204 — Test",
        total_records=1000,
        auto_matched=965,
        pending_review=35,
        approved=0,
        dismissed=0,
        status="completed",
        uploaded_by=analyst_user.id,
        processed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(batch)
    await db_session.commit()
    await db_session.refresh(batch)
    return batch


@pytest.fixture(scope="function")
async def sample_exceptions(
    db_session: AsyncSession,
    sample_batch: ReconciliationBatch,
) -> list[ReconciliationException]:
    """Create sample reconciliation exceptions for a batch."""
    from decimal import Decimal

    exceptions = [
        ReconciliationException(
            batch_id=sample_batch.id,
            exception_status=ExceptionStatus.missing_settlement,
            oracle_ref="TXN-20240601-004891",
            raast_ref="RAAST-REF-88213",
            amount=Decimal("75000.00"),
            currency="PKR",
            transaction_timestamp=datetime.now(timezone.utc),
            match_confidence=Decimal("43.0"),
            exception_reason="Oracle reversal with no settlement counterpart",
            created_at=datetime.now(timezone.utc),
        ),
        ReconciliationException(
            batch_id=sample_batch.id,
            exception_status=ExceptionStatus.likely_duplicate,
            oracle_ref="TXN-20240601-004892",
            amount=Decimal("15000.00"),
            currency="PKR",
            transaction_timestamp=datetime.now(timezone.utc),
            timestamp_gap_seconds=Decimal("4.0"),
            match_confidence=Decimal("67.0"),
            exception_reason="Same amount + account within 60s",
            created_at=datetime.now(timezone.utc),
        ),
        ReconciliationException(
            batch_id=sample_batch.id,
            exception_status=ExceptionStatus.pending_confirmation,
            oracle_ref="TXN-20240601-004900",
            settlement_ref="REV-BATCH-204-LINE-44",
            amount=Decimal("250000.00"),
            currency="PKR",
            transaction_timestamp=datetime.now(timezone.utc),
            timestamp_gap_seconds=Decimal("45.0"),
            match_confidence=Decimal("81.0"),
            exception_reason="Amount matches, timestamp gap > 30s",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    db_session.add_all(exceptions)
    await db_session.commit()
    return exceptions


# ════════════════════════════════════════════════════════════════════════════
# QUARANTINE FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_quarantined_payload(
    db_session: AsyncSession,
) -> QuarantinedPayload:
    """Create and return a sample quarantined payload."""
    payload = QuarantinedPayload(
        id=uuid.UUID("40000000-0000-0000-0000-000000000001"),
        source_system="core_banking",
        original_filename="oracle_batch_test.xml",
        raw_payload="""<?xml version="1.0" encoding="UTF-8"?>
<transaction>
  <id>TXN-TEST-001</id>
  <amount>50000.00</amount>
  <beneficiary_name>Ali & Sons Ltd</beneficiary_name>
  <account>PK36UNIL0000000000009999</account>
  <timestamp>2024-06-01T10:15:00</timestamp>
</transaction>""",
        corrected_payload="""<?xml version="1.0" encoding="UTF-8"?>
<transaction>
  <id>TXN-TEST-001</id>
  <amount>50000.00</amount>
  <beneficiary_name>Ali &amp; Sons Ltd</beneficiary_name>
  <account>PK36UNIL0000000000009999</account>
  <timestamp>2024-06-01T10:15:00</timestamp>
</transaction>""",
        validation_errors=[
            {
                "field": "beneficiary_name",
                "error": "Unescaped '&' character — must be &amp;",
                "value": "&",
                "line_number": 5,
            }
        ],
        error_count=1,
        status=QuarantineStatus.quarantined,
        reprocess_attempts=0,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(payload)
    await db_session.commit()
    await db_session.refresh(payload)
    return payload


# ════════════════════════════════════════════════════════════════════════════
# INGESTION JOB FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_ingestion_job(
    db_session: AsyncSession,
    analyst_user: User,
) -> IngestionJob:
    """Create and return a sample completed ingestion job."""
    job = IngestionJob(
        id=uuid.UUID("50000000-0000-0000-0000-000000000001"),
        filename="oracle_transactions_20240601.csv",
        file_path="ingestion/core_banking/test/oracle_transactions_20240601.csv",
        file_size_bytes=204800,
        source_system=SourceSystem.core_banking,
        status=JobStatus.completed,
        records_total=1000,
        records_processed=998,
        records_failed=2,
        celery_task_id="test-celery-task-abc123",
        job_logs=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Completed: 998 records inserted, 2 failed",
            }
        ],
        uploaded_by=analyst_user.id,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT LIFECYCLE FIXTURE
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def sample_lifecycle(db_session: AsyncSession) -> PaymentLifecycle:
    """Create the demo Rs. 75,000 payment lifecycle (4-system correlation)."""
    from decimal import Decimal

    lifecycle = PaymentLifecycle(
        id=uuid.UUID("60000000-0000-0000-0000-000000000001"),
        canonical_id="PLO-75K-TEST",
        amount=Decimal("75000.00"),
        currency="PKR",
        account_from="PK36UNIL0000000000001234",
        account_to="JC-WALLET-9876543210",
        initiated_at=datetime(2024, 6, 1, 9, 41, 2, tzinfo=timezone.utc),
        status="reversed",
        identifier_map={
            "core_banking": "TXN-20240601-004891",
            "raast": "RAAST-REF-88213",
            "wallet": "JC-TXN-44509",
            "settlement": "REV-BATCH-204-LINE-17",
        },
        lifecycle_graph={
            "nodes": [
                {
                    "id": "TXN-20240601-004891",
                    "source_system": "core_banking",
                    "timestamp": "2024-06-01T09:41:02+00:00",
                    "status": "created",
                    "amount": "75000",
                },
                {
                    "id": "RAAST-REF-88213",
                    "source_system": "raast",
                    "timestamp": "2024-06-01T09:41:04+00:00",
                    "status": "submitted",
                    "amount": "75000",
                },
                {
                    "id": "JC-TXN-44509",
                    "source_system": "wallet",
                    "timestamp": "2024-06-01T09:41:14+00:00",
                    "status": "retry_storm",
                    "amount": "75000",
                },
                {
                    "id": "REV-BATCH-204-LINE-17",
                    "source_system": "settlement",
                    "timestamp": "2024-06-01T09:41:33+00:00",
                    "status": "reversal_matched",
                    "amount": "75000",
                },
            ],
            "edges": [
                {
                    "source": "TXN-20240601-004891",
                    "target": "RAAST-REF-88213",
                    "relationship": "follows",
                },
                {
                    "source": "RAAST-REF-88213",
                    "target": "JC-TXN-44509",
                    "relationship": "follows",
                },
                {
                    "source": "JC-TXN-44509",
                    "target": "REV-BATCH-204-LINE-17",
                    "relationship": "follows",
                },
            ],
        },
        timeline_events=[
            {
                "timestamp": "2024-06-01T09:41:02+00:00",
                "source_system": "core_banking",
                "transaction_id": "TXN-20240601-004891",
                "status": "created",
                "event": "Created in Core Banking (Oracle)",
            },
            {
                "timestamp": "2024-06-01T09:41:04+00:00",
                "source_system": "raast",
                "transaction_id": "RAAST-REF-88213",
                "status": "submitted",
                "event": "Submitted to RAAST Gateway",
            },
            {
                "timestamp": "2024-06-01T09:41:09+00:00",
                "source_system": "raast",
                "transaction_id": "RAAST-REF-88213",
                "status": "latency_anomaly",
                "event": "RAAST latency: 2,200ms — ANOMALY",
            },
            {
                "timestamp": "2024-06-01T09:41:14+00:00",
                "source_system": "wallet",
                "transaction_id": "JC-TXN-44509",
                "status": "retry",
                "event": "Wallet retry #1 → #2 → #3",
            },
            {
                "timestamp": "2024-06-01T09:41:32+00:00",
                "source_system": "raast",
                "transaction_id": "RAAST-REF-88213",
                "status": "reversed",
                "event": "Transaction reversed by RAAST",
            },
        ],
        correlation_confidence=Decimal("97.5"),
        source_count=4,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(lifecycle)
    await db_session.commit()
    await db_session.refresh(lifecycle)
    return lifecycle


# ════════════════════════════════════════════════════════════════════════════
# MOCK FIXTURES — External Services
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_supabase_storage():
    """Mock Supabase Storage so tests don't make real API calls."""
    with patch("app.utils.storage._get_supabase_client") as mock:
        client = MagicMock()
        client.storage.from_.return_value.upload.return_value = {"Key": "test/path.csv"}
        client.storage.from_.return_value.download.return_value = b"test,data\n1,2"
        client.storage.from_.return_value.remove.return_value = [{"name": "test/path.csv"}]
        mock.return_value = client
        yield mock


@pytest.fixture
def mock_celery_task():
    """Mock Celery task .delay() so tests don't actually queue tasks."""
    mock_result = MagicMock()
    mock_result.id = "test-celery-task-id-abc123"
    return mock_result


@pytest.fixture
def mock_groq_response():
    """Mock Groq API response for AI summary tests."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "SENTINEL INCIDENT REPORT — Auto-generated 09:42:18\n\n"
        "RAAST processing latency increased 175% above baseline at 09:41. "
        "850 transactions affected. Estimated settlement impact: Rs. 18.5M. "
        "Playbook P-007 recommended. All figures sourced from Sentinel telemetry."
    )
    return mock_response


@pytest.fixture
def mock_groq_client(mock_groq_response):
    """Mock the entire Groq client for AI tests."""
    with patch("app.core.ai_summarizer.AsyncGroq") as mock_groq:
        instance = AsyncMock()
        instance.chat.completions.create = AsyncMock(
            return_value=mock_groq_response
        )
        mock_groq.return_value = instance
        yield instance


@pytest.fixture
def mock_redis():
    """Mock Redis for cache tests."""
    with patch("app.utils.cache._get_redis") as mock:
        redis_instance = AsyncMock()
        redis_instance.get.return_value = None
        redis_instance.setex.return_value = True
        redis_instance.delete.return_value = 1
        redis_instance.ping.return_value = True
        redis_instance.keys.return_value = []
        redis_instance.aclose = AsyncMock()
        mock.return_value = redis_instance
        yield redis_instance


# ════════════════════════════════════════════════════════════════════════════
# UTILITY FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_csv_content() -> bytes:
    """Sample CSV file content for ingestion tests."""
    return (
        b"txn_id,amount,currency,account_from,account_to,"
        b"txn_timestamp,txn_status\n"
        b"TXN-20240601-004891,75000.00,PKR,PK36UNIL0001,"
        b"JC-9876543210,2024-06-01T09:41:02,created\n"
        b"RAAST-REF-88213,75000.00,PKR,PK36UNIL0001,"
        b"JC-9876543210,2024-06-01T09:41:04,submitted\n"
        b"JC-TXN-44509,75000.00,PKR,PK36UNIL0001,"
        b"JC-9876543210,2024-06-01T09:41:14,retry\n"
        b"REV-BATCH-204-LINE-17,75000.00,PKR,PK36UNIL0001,"
        b"JC-9876543210,2024-06-01T09:41:33,reversed\n"
    )


@pytest.fixture
def sample_xml_content() -> bytes:
    """Sample Oracle XML payload content."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<transactions>
  <transaction>
    <id>TXN-20240601-004891</id>
    <amount>75000.00</amount>
    <currency>PKR</currency>
    <account_from>PK36UNIL0000000000001234</account_from>
    <account_to>JC-WALLET-9876543210</account_to>
    <timestamp>2024-06-01T09:41:02</timestamp>
    <status>created</status>
    <beneficiary_name>Test Customer</beneficiary_name>
  </transaction>
</transactions>"""


@pytest.fixture
def malformed_xml_content() -> bytes:
    """Sample malformed Oracle XML payload with unescaped characters."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<transaction>
  <id>TXN-MALFORMED-001</id>
  <amount>50000.00</amount>
  <account>PK36UNIL0000000000009999</account>
  <timestamp>2024-06-01T10:15:00</timestamp>
  <beneficiary_name>Ali & Sons <Ltd></beneficiary_name>
</transaction>"""


@pytest.fixture
def sample_incident_data() -> dict:
    """Structured incident data dict for AI summary tests."""
    return {
        "incident_id": "10000000-0000-0000-0000-000000000001",
        "title": "RAAST Gateway Timeout → Retry Storm",
        "incident_type": "raast_timeout",
        "severity": "critical",
        "source_system": "raast",
        "transactions_affected": 850,
        "customers_affected": 412,
        "estimated_amount_pkr": 18500000.0,
        "projected_transactions_25min": 11200,
        "detected_at": "2024-06-01T09:41:34+00:00",
        "description": "RAAST latency spiked 175% above baseline",
    }


# ════════════════════════════════════════════════════════════════════════════
# PYTEST CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require external services"
    )
    config.addinivalue_line(
        "markers",
        "unit: marks pure unit tests with no DB or network"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark async tests."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)