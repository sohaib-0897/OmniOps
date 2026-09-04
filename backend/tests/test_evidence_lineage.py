import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, Workspace
from app.models.document import SourceDocument, DocumentChunk
from app.models.investigation import InvestigationSession, InvestigationStatus
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim, EpistemicType

@pytest.mark.asyncio
async def test_evidence_lineage_graph_api(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    auth_headers: dict
):
    # 1. Create Session
    session = InvestigationSession(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        objective="Lineage test: Enterprise sales decline",
        status=InvestigationStatus.COMPLETED.value
    )
    db_session.add(session)
    await db_session.flush()

    # 2. Create Source & Chunk
    source = SourceDocument(
        workspace_id=test_workspace.id,
        file_name="financial_q3.pdf",
        storage_path="/storage/financial_q3.pdf",
        mime_type="application/pdf",
        byte_size=10240,
        sha256_hash="abcdef1234567890",
        modality="pdf",
        processing_status="ready"
    )
    db_session.add(source)
    await db_session.flush()

    chunk = DocumentChunk(
        workspace_id=test_workspace.id,
        source_id=source.id,
        chunk_index=0,
        content="Q3 Enterprise software revenue contracted by 33.3% YoY to $4.2M.",
        modality="pdf",
        page_number=14
    )
    db_session.add(chunk)
    await db_session.flush()

    # 3. Create Evidence Item
    ev_item = EvidenceItem(
        session_id=session.id,
        source_id=source.id,
        chunk_id=chunk.id,
        page_number=14,
        exact_quote="Q3 Enterprise software revenue contracted by 33.3% YoY to $4.2M.",
        confidence_score=0.98
    )
    db_session.add(ev_item)
    await db_session.flush()

    # 4. Create Calculation Record
    calc = CalculationRecord(
        session_id=session.id,
        calculation_type="sql_query",
        formula_or_code="SELECT (4.2 - 6.3) / 6.3 * 100",
        input_values={"q2": 6.3, "q3": 4.2},
        computed_output=-33.33,
        reproducibility_hash="hash_repro_12345"
    )
    db_session.add(calc)
    await db_session.flush()

    # 5. Create Verified Claim
    claim = VerifiedClaim(
        session_id=session.id,
        claim_id_code="CLM-001",
        statement="Enterprise revenue contracted by 33.33% from Q2 to Q3.",
        epistemic_type=EpistemicType.CALCULATION.value,
        confidence_score=1.0,
        calculation_id=calc.id,
        supporting_citations=[str(ev_item.id)],
        supporting_claims=[]
    )
    db_session.add(claim)
    await db_session.commit()

    # 6. Fetch Lineage Graph via API
    resp = await client.get(f"/api/v1/investigations/{session.id}/evidence", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["session_id"] == str(session.id)
    assert data["claims_count"] == 1
    assert data["citations_count"] == 1
    assert data["calculations_count"] == 1

    # Verify Nodes & Edges
    node_types = [n["type"] for n in data["nodes"]]
    assert "source" in node_types
    assert "evidence" in node_types
    assert "calculation" in node_types
    assert "calculation" in node_types

    edge_relations = [e["relation"] for e in data["edges"]]
    assert "EXTRACTED_FROM" in edge_relations
    assert "CALCULATED_FROM" in edge_relations
    assert "BACKED_BY" in edge_relations
