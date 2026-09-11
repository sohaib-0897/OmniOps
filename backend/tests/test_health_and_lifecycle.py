import uuid
import os
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.models.document import SourceDocument, TabularDataset
from app.core.config import settings

@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert data["data"]["service"] == "OmniOps Backend"

@pytest.mark.asyncio
async def test_parquet_file_unlinking_on_document_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    auth_headers: dict
):
    # 1. Create a dummy source document and associated tabular dataset with parquet file
    parquet_dir = settings.PARQUET_DIR / str(test_workspace.id)
    parquet_dir.mkdir(parents=True, exist_ok=True)
    parquet_file = parquet_dir / f"test_table_{uuid.uuid4().hex[:8]}.parquet"
    
    df = pd.DataFrame({"id": [1, 2, 3], "val": ["a", "b", "c"]})
    df.to_parquet(str(parquet_file), index=False)
    assert parquet_file.exists()

    doc = SourceDocument(
        workspace_id=test_workspace.id,
        file_name="test_data.csv",
        storage_path="/tmp/fake_storage.csv",
        mime_type="text/csv",
        byte_size=100,
        sha256_hash="hash123456",
        modality="spreadsheet",
        processing_status="ready"
    )
    db_session.add(doc)
    await db_session.flush()

    tab = TabularDataset(
        workspace_id=test_workspace.id,
        source_id=doc.id,
        table_name="test_table_autounlink",
        row_count=3,
        column_count=2,
        parquet_storage_path=str(parquet_file),
        schema_definition=[{"name": "id", "type": "int"}, {"name": "val", "type": "str"}]
    )
    db_session.add(tab)
    await db_session.commit()

    # 2. Call delete file endpoint
    del_resp = await client.delete(
        f"/api/v1/workspaces/{test_workspace.id}/files/{doc.id}",
        headers=auth_headers
    )
    assert del_resp.status_code == 200

    # 3. Assert physical parquet file was unlinked
    assert not parquet_file.exists()

@pytest.mark.asyncio
async def test_workspace_list_aggregation_query(
    client: AsyncClient,
    test_workspace: Workspace,
    auth_headers: dict
):
    resp = await client.get("/api/v1/workspaces", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    
    ws_entry = next((w for w in data["data"] if w["id"] == str(test_workspace.id)), None)
    assert ws_entry is not None
    assert "documents_count" in ws_entry
    assert "tables_count" in ws_entry
    assert "user_role" in ws_entry
    assert isinstance(ws_entry["documents_count"], int)
    assert isinstance(ws_entry["tables_count"], int)
