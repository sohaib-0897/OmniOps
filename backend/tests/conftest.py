import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory and repository root to sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
root_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole, UserSession
from app.main import app

# Set test environment
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
        
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="analyst@omniops.ai",
        hashed_password=get_password_hash("SecurePass123!"),
        full_name="Lead Business Analyst"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture(scope="function")
async def test_workspace(db_session: AsyncSession, test_user: User) -> Workspace:
    ws = Workspace(
        name="Global Q3 Revenue Intelligence",
        description="Workspace for analyzing Q3 revenue contraction",
        created_by=test_user.id
    )
    db_session.add(ws)
    await db_session.flush()

    mem = WorkspaceMembership(
        workspace_id=ws.id,
        user_id=test_user.id,
        role=WorkspaceRole.OWNER.value
    )
    db_session.add(mem)
    await db_session.commit()
    await db_session.refresh(ws)
    return ws

@pytest_asyncio.fixture(scope="function")
async def auth_headers(test_user: User, db_session: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    session = UserSession(user_id=test_user.id, expires_at=now + timedelta(days=1), last_used_at=now)
    db_session.add(session); await db_session.commit()
    token = create_access_token(subject=test_user.id, session_id=session.id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# PostgreSQL integration provisioning
#
# Every PostgreSQL suite provisions its own schema through this helper so a
# fresh, dedicated test database is green on its FIRST run. No module may rely
# on another module's fixture having executed first.
# ---------------------------------------------------------------------------

POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


def require_postgres_test_database() -> str:
    """Return the configured integration URL, refusing a non-dedicated database."""
    assert POSTGRES_TEST_URL
    database_name = POSTGRES_TEST_URL.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in database_name.lower():
        pytest.fail(
            "POSTGRES_TEST_DATABASE_URL must point to a dedicated database whose name contains 'test'."
        )
    return POSTGRES_TEST_URL


def run_migrations_to_head(url: str) -> None:
    """Apply the Alembic head to the integration database."""
    import subprocess

    result = subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "test"},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def ensure_postgres_schema(url: str) -> None:
    """Migrate the integration database unless it is already at head.

    Idempotent and order-independent: it is safe to call from every fixture,
    including after another suite has dropped and recreated ``public``.
    """
    from sqlalchemy import text

    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            present = (
                await connection.execute(text("SELECT to_regclass('public.users')"))
            ).scalar()
            revision = None
            if present is not None:
                revision = (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar()
    finally:
        await engine.dispose()
    if present is not None and revision:
        return
    run_migrations_to_head(url)


@pytest_asyncio.fixture
async def postgres_schema() -> str:
    """Provision the integration schema and yield its URL."""
    url = require_postgres_test_database()
    await ensure_postgres_schema(url)
    return url


async def ensure_postgres_tenant(factory):
    """Get-or-create the owning User/Workspace a PostgreSQL suite operates on.

    Suites previously read whichever tenant another module's fixture happened
    to have seeded, which made them order-dependent and made a fresh database
    fail on its first run. Each suite now guarantees its own tenant.
    """
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.user import User, Workspace

    async with factory() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            user = User(
                email=f"pg-suite-{uuid4()}@example.com",
                hashed_password="not-a-login-credential",
                full_name="PostgreSQL Suite",
            )
            db.add(user)
            await db.flush()
        workspace = (
            await db.execute(
                select(Workspace).where(Workspace.created_by == user.id).limit(1)
            )
        ).scalar_one_or_none()
        if workspace is None:
            workspace = Workspace(name="PostgreSQL Suite Workspace", created_by=user.id)
            db.add(workspace)
            await db.flush()
        user_id, workspace_id = user.id, workspace.id
        await db.commit()
        return user_id, workspace_id
