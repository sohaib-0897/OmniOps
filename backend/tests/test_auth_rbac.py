import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole, UserSession
from app.models.investigation import InvestigationSession, InvestigationStatus
from app.core.security import create_access_token, get_password_hash

@pytest.mark.asyncio
async def test_user_registration_and_login(client: AsyncClient):
    # 1. Register
    reg_resp = await client.post("/api/v1/auth/register", json={
        "email": "finance_director@omniops.ai",
        "password": "StrongPassword123!",
        "full_name": "Finance Director"
    })
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["success"] is True
    assert "access_token" in reg_data["data"]["token"]
    assert reg_data["data"]["user"]["email"] == "finance_director@omniops.ai"

    # 2. Login
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "finance_director@omniops.ai",
        "password": "StrongPassword123!"
    })
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["success"] is True
    assert "access_token" in login_data["data"]["token"]

@pytest.mark.asyncio
async def test_workspace_isolation_and_cross_tenant_denial(
    client: AsyncClient, 
    db_session: AsyncSession, 
    test_user: User, 
    test_workspace: Workspace, 
    auth_headers: dict
):
    # Create another unauthorized user and foreign workspace
    other_user = User(
        email="competitor@othercompany.com",
        hashed_password=get_password_hash("OtherPass123!"),
        full_name="External Competitor"
    )
    db_session.add(other_user)
    await db_session.flush()

    foreign_ws = Workspace(
        name="Confidential Competitor Workspace",
        created_by=other_user.id
    )
    db_session.add(foreign_ws)
    await db_session.flush()

    foreign_mem = WorkspaceMembership(
        workspace_id=foreign_ws.id,
        user_id=other_user.id,
        role=WorkspaceRole.OWNER.value
    )
    db_session.add(foreign_mem)
    await db_session.commit()

    # 1. Authorized user can access their own workspace
    resp_ok = await client.get(f"/api/v1/workspaces/{test_workspace.id}", headers=auth_headers)
    assert resp_ok.status_code == 200
    assert resp_ok.json()["data"]["name"] == test_workspace.name

    # 2. Authorized user CANNOT access foreign workspace (Must return 403 Forbidden)
    resp_denied = await client.get(f"/api/v1/workspaces/{foreign_ws.id}", headers=auth_headers)
    assert resp_denied.status_code == 403
    assert "Access denied" in resp_denied.json()["detail"]

@pytest.mark.asyncio
async def test_unauthorized_sse_stream_cross_tenant_denial(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict
):
    # Create external user, foreign workspace, and foreign investigation
    foreign_user = User(
        email="foreign_agent@external.com",
        hashed_password=get_password_hash("Pass123!"),
        full_name="Foreign Agent"
    )
    db_session.add(foreign_user)
    await db_session.flush()

    foreign_ws = Workspace(
        name="Foreign Secret Workspace",
        created_by=foreign_user.id
    )
    db_session.add(foreign_ws)
    await db_session.flush()

    foreign_session = InvestigationSession(
        workspace_id=foreign_ws.id,
        user_id=foreign_user.id,
        objective="Secret foreign analysis",
        status=InvestigationStatus.PLANNING.value
    )
    db_session.add(foreign_session)
    await db_session.commit()

    # Attempt to stream foreign investigation using test_user token
    resp = await client.get(f"/api/v1/investigations/{foreign_session.id}/stream", headers=auth_headers)
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_viewer_role_mutating_restrictions(
    client: AsyncClient,
    db_session: AsyncSession,
    test_workspace: Workspace
):
    # Create Viewer user in test_workspace
    viewer_user = User(
        email="viewer_auditor@company.com",
        hashed_password=get_password_hash("ViewerPass123!"),
        full_name="Viewer Auditor"
    )
    db_session.add(viewer_user)
    await db_session.flush()

    viewer_mem = WorkspaceMembership(
        workspace_id=test_workspace.id,
        user_id=viewer_user.id,
        role=WorkspaceRole.VIEWER.value
    )
    db_session.add(viewer_mem)
    await db_session.commit()

    now = datetime.now(timezone.utc); viewer_session = UserSession(user_id=viewer_user.id, expires_at=now + timedelta(days=1), last_used_at=now); db_session.add(viewer_session); await db_session.commit()
    viewer_token = create_access_token(subject=viewer_user.id, session_id=viewer_session.id)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # 1. Viewer CAN read workspace details
    read_resp = await client.get(f"/api/v1/workspaces/{test_workspace.id}", headers=viewer_headers)
    assert read_resp.status_code == 200

    # 2. Viewer CANNOT create investigations (requires Editor role)
    create_resp = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/investigations",
        headers=viewer_headers,
        json={"objective": "Unauthorized attempt"}
    )
    assert create_resp.status_code == 403
    assert "requires 'editor' role" in create_resp.json()["detail"]

    # 3. Viewer CANNOT upload files (requires Editor role)
    upload_resp = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/files",
        headers=viewer_headers,
        files={"file": ("test.txt", b"content", "text/plain")}
    )
    assert upload_resp.status_code == 403
    assert "requires 'editor' role" in upload_resp.json()["detail"]
