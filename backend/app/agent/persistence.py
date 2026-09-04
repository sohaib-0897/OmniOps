"""Authoritative idempotent domain-output persistence boundaries."""
from __future__ import annotations
from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.runtime import logical_identity, get_or_create_logical_output, persist_runtime_event
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim, ContradictionRecord
from app.models.investigation import InvestigationSession


async def persist_evidence(session: AsyncSession, *, session_id: UUID, workspace_id: UUID, source_id: UUID, chunk_id: Optional[UUID], locator: Dict[str, Any], **values: Any) -> EvidenceItem:
    identity = logical_identity(workspace_id, session_id, source_id, chunk_id, locator)
    return await get_or_create_logical_output(session, EvidenceItem, session_id, identity, source_id=source_id, chunk_id=chunk_id, **values)


async def persist_calculation(session: AsyncSession, *, session_id: UUID, step_id: str, formula: str, inputs: Any, **values: Any) -> CalculationRecord:
    identity = logical_identity(session_id, step_id, formula, inputs)
    return await get_or_create_logical_output(session, CalculationRecord, session_id, identity, formula_or_code=formula, input_values=inputs, **values)


async def persist_claim(session: AsyncSession, *, session_id: UUID, step_id: str, statement: str, lineage: Any, **values: Any) -> VerifiedClaim:
    identity = logical_identity(session_id, step_id, statement.strip().lower(), lineage)
    return await get_or_create_logical_output(session, VerifiedClaim, session_id, identity, claim_id_code=values.pop("claim_id_code", identity[:12]), statement=statement, **values)


async def persist_contradiction(session: AsyncSession, *, investigation_id: UUID, topic: str, evidence_a_id: UUID, evidence_b_id: UUID, **values: Any) -> ContradictionRecord:
    a, b = sorted((str(evidence_a_id), str(evidence_b_id)))
    identity = logical_identity(investigation_id, topic.strip().lower(), a, b)
    # ContradictionRecord has no identity column; enforce replay safety by querying the normalized pair.
    from sqlalchemy import select
    existing = (await session.execute(select(ContradictionRecord).where(ContradictionRecord.investigation_id == investigation_id, ContradictionRecord.evidence_a_id == UUID(a), ContradictionRecord.evidence_b_id == UUID(b), ContradictionRecord.topic == topic))).scalar_one_or_none()
    if existing:
        return existing
    record = ContradictionRecord(investigation_id=investigation_id, topic=topic, evidence_a_id=UUID(a), evidence_b_id=UUID(b), conflict_type=values.pop("conflict_type", "CONFLICT"), status="UNRESOLVED", logical_identity=identity, created_at=values.pop("created_at", datetime.now(timezone.utc)))
    session.add(record)
    await session.flush()
    await persist_runtime_event(
        session,
        investigation_id,
        "contradiction.created",
        logical_identity(investigation_id, "contradiction.created", identity),
        {"topic": topic, "evidence_a_id": a, "evidence_b_id": b},
        record.id,
    )
    return record


async def finalize_synthesis(session: AsyncSession, investigation: InvestigationSession, output: Dict[str, Any], plan_version: int) -> Dict[str, Any]:
    """Idempotent authoritative final output; retries return the committed result."""
    identity = logical_identity(investigation.id, plan_version, output)
    if investigation.synthesis_identity == identity and investigation.final_response is not None:
        return investigation.final_response
    investigation.synthesis_identity = identity
    investigation.final_response = output
    await session.flush()
    return output
