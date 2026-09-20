"""Authoritative idempotent domain-output persistence boundaries."""
from __future__ import annotations
from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.runtime import logical_identity, get_or_create_logical_output, persist_runtime_event
from app.models.evidence import (
    EvidenceItem,
    CalculationRecord,
    VerifiedClaim,
    ContradictionRecord,
    InferenceRecord,
    RecommendationRecord,
)
from app.models.investigation import InvestigationSession
from app.evidence.validator import validate_claim_proposal
from app.evidence.calculation_identity import calculation_reproducibility_hash


async def persist_evidence(session: AsyncSession, *, session_id: UUID, workspace_id: UUID, source_id: UUID, chunk_id: Optional[UUID], locator: Dict[str, Any], **values: Any) -> EvidenceItem:
    identity = logical_identity(workspace_id, session_id, source_id, chunk_id, locator)
    return await get_or_create_logical_output(session, EvidenceItem, session_id, identity, source_id=source_id, chunk_id=chunk_id, **values)


async def persist_tool_domain_outputs(session: AsyncSession, *, investigation: InvestigationSession, step_id: str, result: Any) -> Dict[str, list]:
    """Promote only explicitly structured tool outputs into the evidence contract.

    Tools may return ``evidence``, ``calculations`` and ``claims`` records with
    source lineage. Unstructured output is never interpreted as a claim.
    """
    if not isinstance(result, dict):
        return {"evidence": [], "calculations": [], "claims": []}
    evidence_rows: list[EvidenceItem] = []
    for item in result.get("evidence", []) or []:
        source_id = UUID(str(item["source_id"]))
        chunk_id = UUID(str(item["chunk_id"])) if item.get("chunk_id") else None
        evidence_rows.append(await persist_evidence(
            session,
            session_id=investigation.id,
            workspace_id=investigation.workspace_id,
            source_id=source_id,
            chunk_id=chunk_id,
            locator=item.get("locator", {}),
            exact_quote=item.get("exact_quote"),
            page_number=item.get("page_number"),
            cell_range=item.get("cell_range"),
            audio_start_ms=item.get("audio_start_ms"),
            audio_end_ms=item.get("audio_end_ms"),
            coordinates=item.get("coordinates"),
            confidence_score=item.get("confidence_score"),
        ))
    calculation_rows: list[CalculationRecord] = []
    for item in result.get("calculations", []) or []:
        calculation_rows.append(await persist_calculation(
            session,
            session_id=investigation.id,
            step_id=step_id,
            formula=item["formula"],
            inputs=item.get("inputs", {}),
            calculation_type=item.get("calculation_type", "aggregation"),
            computed_output=item["computed_output"],
            reproducibility_hash=item["reproducibility_hash"],
            evidence_ids=item.get("evidence_ids", []),
            source_ids=item.get("source_ids", []),
        ))
    claim_rows: list[VerifiedClaim] = []
    for item in result.get("claims", []) or []:
        evidence_ids = [str(v) for v in item.get("evidence_ids", [])]
        if not evidence_ids and evidence_rows:
            evidence_ids = [str(row.id) for row in evidence_rows]
        calculation_ids = [str(v) for v in item.get("calculation_ids", [])]
        validation = await validate_claim_proposal(session, investigation.id, evidence_ids, calculation_ids)
        claim_rows.append(await persist_claim(
            session,
            session_id=investigation.id,
            step_id=step_id,
            statement=item["statement"],
            lineage={"evidence_ids": evidence_ids, "calculation_ids": calculation_ids},
            claim_id_code=item.get("claim_id_code"),
            epistemic_type=item.get("epistemic_type", "fact"),
            verification_status="VERIFIED" if validation.valid else "REJECTED",
            verification_errors=validation.errors,
            supporting_citations=evidence_ids,
            calculation_ids=calculation_ids,
        ))
    return {"evidence": evidence_rows, "calculations": calculation_rows, "claims": claim_rows}


async def persist_calculation(session: AsyncSession, *, session_id: UUID, step_id: str, formula: str, inputs: Any, **values: Any) -> CalculationRecord:
    computed_output = values.get("computed_output")
    values.pop("reproducibility_hash", None)
    values["reproducibility_hash"] = calculation_reproducibility_hash(
        formula,
        inputs,
        computed_output,
    )
    identity = logical_identity(session_id, step_id, formula, inputs)
    return await get_or_create_logical_output(session, CalculationRecord, session_id, identity, formula_or_code=formula, input_values=inputs, **values)


async def persist_claim(session: AsyncSession, *, session_id: UUID, step_id: str, statement: str, lineage: Any, **values: Any) -> VerifiedClaim:
    identity = logical_identity(session_id, step_id, statement.strip().lower(), lineage)
    return await get_or_create_logical_output(session, VerifiedClaim, session_id, identity, claim_id_code=values.pop("claim_id_code", None) or identity[:12], statement=statement, **values)


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


async def invalidate_source_dependents(
    session: AsyncSession,
    *,
    source_id: UUID,
    reason: str = "SOURCE_DELETED",
) -> None:
    """Reject persisted conclusions whose lineage is removed with a source."""
    from sqlalchemy import select

    evidence = (
        await session.execute(select(EvidenceItem).where(EvidenceItem.source_id == source_id))
    ).scalars().all()
    if not evidence:
        return
    evidence_ids = {str(item.id) for item in evidence}
    session_ids = {item.session_id for item in evidence}
    calculations = (
        await session.execute(
            select(CalculationRecord).where(CalculationRecord.session_id.in_(session_ids))
        )
    ).scalars().all()
    invalid_calculation_ids = {
        str(item.id)
        for item in calculations
        if evidence_ids.intersection(str(value) for value in item.evidence_ids)
        or str(source_id) in {str(value) for value in item.source_ids}
    }
    claims = (
        await session.execute(
            select(VerifiedClaim).where(VerifiedClaim.session_id.in_(session_ids))
        )
    ).scalars().all()
    rejected_codes: set[str] = set()
    for claim in claims:
        if evidence_ids.intersection(str(value) for value in claim.supporting_citations) or invalid_calculation_ids.intersection(
            str(value) for value in claim.calculation_ids
        ):
            claim.verification_status = "REJECTED"
            claim.verification_errors = list(dict.fromkeys([*(claim.verification_errors or []), reason]))
            rejected_codes.add(claim.claim_id_code)

    inferences = (
        await session.execute(
            select(InferenceRecord).where(InferenceRecord.session_id.in_(session_ids))
        )
    ).scalars().all()
    rejected_inferences: set[str] = set()
    for inference in inferences:
        if rejected_codes.intersection(inference.supporting_claim_ids or []):
            inference.verification_status = "REJECTED"
            inference.verification_errors = list(dict.fromkeys([*(inference.verification_errors or []), reason]))
            rejected_inferences.add(inference.inference_id_code)

    recommendations = (
        await session.execute(
            select(RecommendationRecord).where(RecommendationRecord.session_id.in_(session_ids))
        )
    ).scalars().all()
    for recommendation in recommendations:
        if rejected_codes.intersection(recommendation.supporting_claim_ids or []) or rejected_inferences.intersection(
            recommendation.supporting_inference_ids or []
        ):
            recommendation.verification_status = "REJECTED"
            recommendation.verification_errors = list(
                dict.fromkeys([*(recommendation.verification_errors or []), reason])
            )

    investigations = (
        await session.execute(
            select(InvestigationSession).where(InvestigationSession.id.in_(session_ids))
        )
    ).scalars().all()
    for investigation in investigations:
        report = dict(investigation.final_response or {})
        if not report:
            continue
        report_claims = []
        for claim in report.get("claims", []) or []:
            value = dict(claim)
            code = str(value.get("claim_id") or value.get("claim_id_code") or "")
            if code in rejected_codes:
                value["verification_status"] = "REJECTED"
                value["verification_errors"] = list(
                    dict.fromkeys([*(value.get("verification_errors") or []), reason])
                )
            report_claims.append(value)
        report["claims"] = report_claims
        report["missing_data_warnings"] = list(
            dict.fromkeys([*(report.get("missing_data_warnings") or []), "A supporting source was deleted; affected findings are no longer verified."])
        )
        investigation.final_response = report


async def finalize_synthesis(session: AsyncSession, investigation: InvestigationSession, output: Dict[str, Any], plan_version: int, worker_id: Optional[str] = None) -> Dict[str, Any]:
    """Idempotent authoritative final output; retries return the committed result."""
    from sqlalchemy import select, update
    from app.agent.runtime import RuntimeErrorCode

    identity = logical_identity(investigation.id, plan_version, output)
    expected_worker = worker_id or investigation.worker_id
    if expected_worker:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            update(InvestigationSession)
            .where(
                InvestigationSession.id == investigation.id,
                InvestigationSession.worker_id == expected_worker,
                InvestigationSession.lease_expires_at >= now,
            )
            .values(synthesis_identity=identity, final_response=output)
        )
        if not result.rowcount:
            raise RuntimeError(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(investigation, "synthesis_identity", identity)
        set_committed_value(investigation, "final_response", output)
        return output

    current = (
        await session.execute(
            select(InvestigationSession.worker_id).where(InvestigationSession.id == investigation.id)
        )
    ).scalar_one()
    if current is not None:
        raise RuntimeError(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
    if investigation.synthesis_identity == identity and investigation.final_response is not None:
        return investigation.final_response
    investigation.synthesis_identity = identity
    investigation.final_response = output
    await session.flush()
    return output
