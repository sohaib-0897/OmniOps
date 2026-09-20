import uuid
from dataclasses import dataclass, field
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk, SourceDocument
from app.models.evidence import CalculationRecord, EvidenceItem, VerifiedClaim, InferenceRecord
from app.models.investigation import InvestigationSession
from app.evidence.calculation_identity import calculation_reproducibility_hash


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)


def _uuid(value: str, kind: str, errors: List[str]):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        errors.append(f"INVALID_{kind}_ID:{value}")
        return None


async def validate_claim_proposal(
    db: AsyncSession, session_id: uuid.UUID, evidence_ids: Iterable[str], calculation_ids: Iterable[str]
) -> ValidationResult:
    """Resolve every proposal reference through its investigation, content, source, and workspace."""
    errors: List[str] = []
    session = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == session_id))).scalar_one_or_none()
    if not session:
        return ValidationResult(False, ["INVESTIGATION_NOT_FOUND"])

    evidence_refs = list(dict.fromkeys(str(v) for v in evidence_ids))
    calculation_refs = list(dict.fromkeys(str(v) for v in calculation_ids))
    if not evidence_refs and not calculation_refs:
        errors.append("UNSUPPORTED_CLAIM")

    for raw_id in evidence_refs:
        evidence_id = _uuid(raw_id.removeprefix("ev_"), "EVIDENCE", errors)
        if not evidence_id:
            continue
        row = (await db.execute(
            select(EvidenceItem, DocumentChunk, SourceDocument)
            .join(DocumentChunk, EvidenceItem.chunk_id == DocumentChunk.id)
            .join(SourceDocument, EvidenceItem.source_id == SourceDocument.id)
            .where(EvidenceItem.id == evidence_id)
        )).first()
        if not row:
            errors.append(f"EVIDENCE_NOT_FOUND:{raw_id}")
            continue
        evidence, content, source = row
        if evidence.session_id != session_id:
            errors.append(f"CROSS_INVESTIGATION_EVIDENCE:{raw_id}")
        if source.workspace_id != session.workspace_id or content.workspace_id != session.workspace_id:
            errors.append(f"CROSS_WORKSPACE_EVIDENCE:{raw_id}")
        if content.source_id != source.id or evidence.source_id != source.id:
            errors.append(f"BROKEN_EVIDENCE_SOURCE_CHAIN:{raw_id}")
        if not evidence.exact_quote or evidence.exact_quote not in content.content:
            errors.append(f"EVIDENCE_CONTENT_MISMATCH:{raw_id}")

    for raw_id in calculation_refs:
        calculation_id = _uuid(raw_id.removeprefix("calc_"), "CALCULATION", errors)
        if not calculation_id:
            continue
        calculation = (await db.execute(
            select(CalculationRecord).where(CalculationRecord.id == calculation_id)
        )).scalar_one_or_none()
        if not calculation:
            errors.append(f"CALCULATION_NOT_FOUND:{raw_id}")
            continue
        if calculation.session_id != session_id:
            errors.append(f"CROSS_INVESTIGATION_CALCULATION:{raw_id}")
        if not calculation.formula_or_code or calculation.computed_output is None or not calculation.reproducibility_hash:
            errors.append(f"INCOMPLETE_CALCULATION:{raw_id}")
        elif calculation.reproducibility_hash != calculation_reproducibility_hash(
            calculation.formula_or_code,
            calculation.input_values,
            calculation.computed_output,
        ):
            errors.append(f"CALCULATION_REPRODUCIBILITY_MISMATCH:{raw_id}")
        if not calculation.evidence_ids and not calculation.source_ids:
            errors.append(f"CALCULATION_INPUT_PROVENANCE_MISSING:{raw_id}")
        nested = await validate_evidence_references(db, session, calculation.evidence_ids)
        errors.extend(f"CALCULATION_{error}" for error in nested)
        for source_ref in calculation.source_ids:
            source_id = _uuid(str(source_ref).removeprefix("src_"), "SOURCE", errors)
            if not source_id:
                continue
            source = (await db.execute(select(SourceDocument).where(SourceDocument.id == source_id))).scalar_one_or_none()
            if not source:
                errors.append(f"CALCULATION_SOURCE_NOT_FOUND:{source_ref}")
            elif source.workspace_id != session.workspace_id:
                errors.append(f"CALCULATION_CROSS_WORKSPACE_SOURCE:{source_ref}")

    return ValidationResult(not errors, errors)


async def validate_evidence_references(db: AsyncSession, session: InvestigationSession, evidence_ids: Iterable[str]) -> List[str]:
    errors: List[str] = []
    for raw_id in evidence_ids:
        evidence_id = _uuid(str(raw_id).removeprefix("ev_"), "EVIDENCE", errors)
        if not evidence_id:
            continue
        row = (await db.execute(
            select(EvidenceItem, DocumentChunk, SourceDocument)
            .join(DocumentChunk, EvidenceItem.chunk_id == DocumentChunk.id)
            .join(SourceDocument, EvidenceItem.source_id == SourceDocument.id)
            .where(EvidenceItem.id == evidence_id)
        )).first()
        if not row:
            errors.append(f"EVIDENCE_NOT_FOUND:{raw_id}")
            continue
        evidence, content, source = row
        if evidence.session_id != session.id:
            errors.append(f"CROSS_INVESTIGATION_EVIDENCE:{raw_id}")
        if source.workspace_id != session.workspace_id or content.workspace_id != session.workspace_id:
            errors.append(f"CROSS_WORKSPACE_EVIDENCE:{raw_id}")
        if content.source_id != source.id or evidence.source_id != source.id:
            errors.append(f"BROKEN_EVIDENCE_SOURCE_CHAIN:{raw_id}")
        if not evidence.exact_quote or evidence.exact_quote not in content.content:
            errors.append(f"EVIDENCE_CONTENT_MISMATCH:{raw_id}")
    return errors


async def validate_supporting_claims(db: AsyncSession, session_id: uuid.UUID, claim_codes: Iterable[str]) -> ValidationResult:
    errors = []
    codes = list(dict.fromkeys(claim_codes))
    if not codes:
        return ValidationResult(False, ["UNSUPPORTED_INFERENCE"])
    for code in codes:
        claim = (await db.execute(select(VerifiedClaim).where(
            VerifiedClaim.session_id == session_id,
            VerifiedClaim.claim_id_code == code,
            VerifiedClaim.verification_status == "VERIFIED",
        ))).scalar_one_or_none()
        if not claim:
            errors.append(f"VERIFIED_CLAIM_NOT_FOUND:{code}")
    return ValidationResult(not errors, errors)


async def validate_recommendation_support(db: AsyncSession, session_id: uuid.UUID, claim_codes: Iterable[str], inference_codes: Iterable[str]) -> ValidationResult:
    claim_codes = list(claim_codes)
    inference_codes = list(inference_codes)
    if not claim_codes and not inference_codes:
        return ValidationResult(False, ["UNSUPPORTED_RECOMMENDATION"])
    claim_result = await validate_supporting_claims(db, session_id, claim_codes)
    errors = list(claim_result.errors)
    for code in dict.fromkeys(inference_codes):
        inference = (await db.execute(select(InferenceRecord).where(
            InferenceRecord.session_id == session_id,
            InferenceRecord.inference_id_code == code,
            InferenceRecord.verification_status == "VERIFIED",
        ))).scalar_one_or_none()
        if not inference:
            errors.append(f"VERIFIED_INFERENCE_NOT_FOUND:{code}")
    return ValidationResult(not errors, errors)
