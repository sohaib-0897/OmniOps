import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import WorkspaceMembership
from app.models.document import TabularDataset
from app.schemas.document import TabularDatasetResponse, TableQueryRequest, TablePreviewResponse
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_workspace_membership
from app.tools.duckdb_tool import DuckDBTool

router = APIRouter(prefix="/workspaces/{workspace_id}/tables", tags=["Tabular Datasets"])

@router.get("", response_model=ResponseEnvelope[List[TabularDatasetResponse]])
async def list_workspace_tables(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """List all registered tabular datasets for the workspace."""
    stmt = select(TabularDataset).where(TabularDataset.workspace_id == workspace_id)
    tables = (await db.execute(stmt)).scalars().all()
    return ResponseEnvelope.ok([TabularDatasetResponse.model_validate(t) for t in tables])

@router.get("/{table_id}/preview", response_model=ResponseEnvelope[TablePreviewResponse])
async def get_table_preview(
    workspace_id: uuid.UUID,
    table_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """Get sample rows and schema definition for a tabular dataset."""
    table = (await db.execute(
        select(TabularDataset).where(
            TabularDataset.id == table_id,
            TabularDataset.workspace_id == workspace_id
        )
    )).scalar_one_or_none()

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table dataset not found in workspace."
        )

    # Query 50 sample rows via DuckDB
    tool = DuckDBTool({table.table_name: table.parquet_storage_path})
    result = tool.execute_query(f"SELECT * FROM {table.table_name} LIMIT 50;")

    return ResponseEnvelope.ok(TablePreviewResponse(
        table_name=table.table_name,
        row_count=table.row_count,
        column_count=table.column_count,
        columns=result.columns or [],
        sample_rows=result.data or [],
        schema_definition=table.schema_definition
    ))

@router.post("/query", response_model=ResponseEnvelope[Dict[str, Any]])
async def run_analytical_sql(
    workspace_id: uuid.UUID,
    req: TableQueryRequest,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """Run read-only analytical SQL query against registered workspace datasets."""
    stmt = select(TabularDataset).where(TabularDataset.workspace_id == workspace_id)
    tables = (await db.execute(stmt)).scalars().all()
    
    if not tables:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tabular datasets registered in this workspace."
        )

    table_map = {t.table_name: t.parquet_storage_path for t in tables}
    tool = DuckDBTool(table_map)
    result = tool.execute_query(req.sql_query, max_rows=200)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "SQL execution failed."
        )

    return ResponseEnvelope.ok({
        "columns": result.columns,
        "rows": result.data,
        "row_count": result.row_count,
        "duration_ms": result.duration_ms,
        "reproducibility_hash": result.reproducibility_hash
    })
