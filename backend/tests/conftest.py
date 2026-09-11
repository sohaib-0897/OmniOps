import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory to sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

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
