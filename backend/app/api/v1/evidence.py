import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User, WorkspaceMembership
from app.models.investigation import InvestigationSession
from app.models.document import SourceDocument, DocumentChunk
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim, InferenceRecord, RecommendationRecord
from app.schemas.evidence import (
    EvidenceLineageGraphResponse, 
    LineageNode, 
    LineageEdge, 
    VerifiedClaimResponse,
    EvidenceItemResponse,
    CalculationRecordResponse
)
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_current_user

router = APIRouter(prefix="/investigations/{investigation_id}", tags=["Evidence & Lineage"])

@router.get("/evidence", response_model=ResponseEnvelope[EvidenceLineageGraphResponse])
async def get_evidence_lineage_graph(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Build and return complete 7-stage Evidence Lineage Graph for the investigation."""
    session = (await db.execute(
        select(InvestigationSession).where(InvestigationSession.id == investigation_id)
    )).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")

    # Membership check
    mem = (await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == session.workspace_id,
            WorkspaceMembership.user_id == current_user.id
        )
    )).scalar_one_or_none()

    if not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    # Fetch all lineage components
    claims = (await db.execute(
        select(VerifiedClaim).where(VerifiedClaim.session_id == investigation_id)
    )).scalars().all()

    evidence_items = (await db.execute(
        select(EvidenceItem, SourceDocument.file_name, SourceDocument.modality, DocumentChunk)
        .join(SourceDocument, EvidenceItem.source_id == SourceDocument.id)
        .join(DocumentChunk, EvidenceItem.chunk_id == DocumentChunk.id)
        .where(EvidenceItem.session_id == investigation_id)
    )).all()

    calculations = (await db.execute(
        select(CalculationRecord).where(CalculationRecord.session_id == investigation_id)
    )).scalars().all()
    inferences = (await db.execute(select(InferenceRecord).where(InferenceRecord.session_id == investigation_id))).scalars().all()
    recommendations = (await db.execute(select(RecommendationRecord).where(RecommendationRecord.session_id == investigation_id))).scalars().all()

    nodes: List[LineageNode] = []
    edges: List[LineageEdge] = []
    seen_sources = set()

    # 1. Evidence Nodes & Source Nodes
    for ev, file_name, modality, content in evidence_items:
        src_node_id = f"src_{ev.source_id}"
        if src_node_id not in seen_sources:
            nodes.append(LineageNode(
                id=src_node_id,
                type="source",
                label=file_name,
                data={"source_id": str(ev.source_id), "modality": modality}
            ))
            seen_sources.add(src_node_id)

        content_node_id = f"content_{content.id}"
        nodes.append(LineageNode(
            id=content_node_id, type="extracted_content", label=f"Extracted content #{content.chunk_index}",
            data={"content_id": str(content.id), "locator": {"page_number": content.page_number, "cell_range": content.cell_range, "audio_start_ms": content.audio_start_ms, "audio_end_ms": content.audio_end_ms}, "extraction_method": content.extraction_method, "content": content.content}
        ))
        edges.append(LineageEdge(source=src_node_id, target=content_node_id, relation="EXTRACTED_FROM"))

        ev_node_id = f"ev_{ev.id}"
        coord_label = f"p.{ev.page_number}" if ev.page_number else (ev.cell_range or f"{ev.audio_start_ms or 0}ms")
        nodes.append(LineageNode(
            id=ev_node_id,
            type="evidence",
            label=f"Quote ({coord_label})",
            data={
                "quote": ev.exact_quote,
                "coordinates": ev.coordinates,
                "confidence": ev.confidence_score
            }
        ))
        edges.append(LineageEdge(
            source=content_node_id,
            target=ev_node_id,
            relation="SUPPORTED_BY_CONTENT"
        ))

    # 2. Calculation Nodes
    for calc in calculations:
        calc_node_id = f"calc_{calc.id}"
        nodes.append(LineageNode(
            id=calc_node_id,
            type="calculation",
            label=f"Calc ({calc.calculation_type})",
            data={
                "code": calc.formula_or_code,
                "output": calc.computed_output,
                "reproducibility_hash": calc.reproducibility_hash
            }
        ))
        for evidence_id in calc.evidence_ids:
            edges.append(LineageEdge(source=f"ev_{str(evidence_id).removeprefix('ev_')}", target=calc_node_id, relation="INPUT_TO"))
        for source_id in calc.source_ids:
            edges.append(LineageEdge(source=f"src_{str(source_id).removeprefix('src_')}", target=calc_node_id, relation="INPUT_TO"))

    # 3. Claim Nodes
    for cl in claims:
        cl_node_id = f"claim_{cl.id}"
        nodes.append(LineageNode(
            id=cl_node_id,
            type=cl.epistemic_type,
            label=f"{cl.claim_id_code} [{cl.epistemic_type.upper()}]",
            data={
                "statement": cl.statement,
                "confidence": cl.confidence_score,
                "claim_code": cl.claim_id_code,
                "verification_status": cl.verification_status,
                "verification_errors": cl.verification_errors,
            }
        ))

        # Edges from calculation to claim
        for calculation_id in cl.calculation_ids or ([str(cl.calculation_id)] if cl.calculation_id else []):
            edges.append(LineageEdge(
                source=f"calc_{calculation_id}",
                target=cl_node_id,
                relation="CALCULATED_FROM"
            ))

        # Edges from evidence citations to claim
        for cit_id in cl.supporting_citations:
            clean_cit_id = cit_id if str(cit_id).startswith("ev_") else f"ev_{cit_id}"
            edges.append(LineageEdge(
                source=clean_cit_id,
                target=cl_node_id,
                relation="BACKED_BY"
            ))

        # Edges from supporting claims to higher-order inference claims
        for sup_code in cl.supporting_claims:
            sup_claim = next((c for c in claims if c.claim_id_code == sup_code or str(c.id) == sup_code or f"claim_{c.id}" == sup_code), None)
            if sup_claim:
                edges.append(LineageEdge(
                    source=f"claim_{sup_claim.id}",
                    target=cl_node_id,
                    relation="DERIVED_FROM"
                ))

    for inference in inferences:
        node_id = f"inference_{inference.id}"
        nodes.append(LineageNode(id=node_id, type="inference", label=inference.inference_id_code, data={"statement": inference.statement, "verification_status": inference.verification_status, "verification_errors": inference.verification_errors}))
        for claim_code in inference.supporting_claim_ids:
            claim = next((c for c in claims if c.claim_id_code == claim_code), None)
            if claim:
                edges.append(LineageEdge(source=f"claim_{claim.id}", target=node_id, relation="SUPPORTS_INFERENCE"))

    for recommendation in recommendations:
        node_id = f"recommendation_{recommendation.id}"
        nodes.append(LineageNode(id=node_id, type="recommendation", label=recommendation.recommendation_id_code, data={"statement": recommendation.statement, "priority": recommendation.priority, "verification_status": recommendation.verification_status, "verification_errors": recommendation.verification_errors}))
        for claim_code in recommendation.supporting_claim_ids:
            claim = next((c for c in claims if c.claim_id_code == claim_code), None)
            if claim:
                edges.append(LineageEdge(source=f"claim_{claim.id}", target=node_id, relation="SUPPORTS_RECOMMENDATION"))
        for inference_code in recommendation.supporting_inference_ids:
            inference = next((i for i in inferences if i.inference_id_code == inference_code), None)
            if inference:
                edges.append(LineageEdge(source=f"inference_{inference.id}", target=node_id, relation="SUPPORTS_RECOMMENDATION"))

    return ResponseEnvelope.ok(EvidenceLineageGraphResponse(
        session_id=investigation_id,
        nodes=nodes,
        edges=edges,
        claims_count=len(claims),
        citations_count=len(evidence_items),
        calculations_count=len(calculations)
    ))
