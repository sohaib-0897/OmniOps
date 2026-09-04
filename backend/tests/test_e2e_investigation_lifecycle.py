import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.models.investigation import InvestigationSession, InvestigationStatus
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_complete_e2e_investigation_and_lineage_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    auth_headers: dict
):
    # 1. Verify workspace metadata
    ws_resp = await client.get(f"/api/v1/workspaces/{test_workspace.id}", headers=auth_headers)
    assert ws_resp.status_code == 200
    assert ws_resp.json()["data"]["name"] == test_workspace.name

    # 2. Upload CSV file
    csv_content = b"region,sales,profit\nNorth,100000,25000\nSouth,80000,18000\nEast,120000,30000\nWest,95000,22000\n"
    upload_resp = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/files",
        headers=auth_headers,
        files={"file": ("regional_sales.csv", csv_content, "text/csv")}
    )
    assert upload_resp.status_code == 200
    file_data = upload_resp.json()["data"]
    assert file_data["modality"] == "spreadsheet"
    assert file_data["processing_status"] == "ready"

    # 3. Verify registered tables
    tables_resp = await client.get(f"/api/v1/workspaces/{test_workspace.id}/tables", headers=auth_headers)
    assert tables_resp.status_code == 200
    tables = tables_resp.json()["data"]
    assert len(tables) >= 1
    table_id = tables[0]["id"]

    # 4. Preview table sample rows and schema profiling
    preview_resp = await client.get(f"/api/v1/workspaces/{test_workspace.id}/tables/{table_id}/preview", headers=auth_headers)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()["data"]
    assert preview_data["row_count"] == 4
    assert len(preview_data["columns"]) == 3

    # 5. Create Investigation Session
    inv_resp = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/investigations",
        headers=auth_headers,
        json={"objective": "Calculate total profit across all regions and rank regions by margin.", "max_steps": 8}
    )
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()["data"]
    session_id = inv_data["id"]

    # 6. Fetch investigation details
    get_inv_resp = await client.get(f"/api/v1/investigations/{session_id}", headers=auth_headers)
    assert get_inv_resp.status_code == 200
    assert get_inv_resp.json()["data"]["objective"] == "Calculate total profit across all regions and rank regions by margin."
