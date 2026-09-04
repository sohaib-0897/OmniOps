import struct
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence.validator import validate_claim_proposal, validate_supporting_claims
from app.ingestion.audio_parser import parse_audio_recording
from app.ingestion.vision_parser import parse_image_file
from app.llm.base import ProviderError, ProviderState
from app.llm.client import OmniOpsLLMClient
from app.models.document import SourceDocument, DocumentChunk
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim
from app.models.investigation import InvestigationSession
from app.models.user import User, Workspace


async def make_session(db, workspace, user, objective="phase one"):
    session = InvestigationSession(workspace_id=workspace.id, user_id=user.id, objective=objective)
    db.add(session)
    await db.flush()
    return session


async def make_evidence(db, session, workspace, text="Revenue was 10."):
    source = SourceDocument(workspace_id=workspace.id, file_name=f"{uuid.uuid4()}.txt", storage_path="test", mime_type="text/plain", byte_size=len(text), sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    db.add(source)
    await db.flush()
    content = DocumentChunk(workspace_id=workspace.id, source_id=source.id, chunk_index=0, content=text, modality="text", extraction_method="test-fixture")
    db.add(content)
    await db.flush()
    evidence = EvidenceItem(session_id=session.id, source_id=source.id, chunk_id=content.id, exact_quote=text)
    db.add(evidence)
    await db.flush()
    return evidence


@pytest.mark.asyncio
async def test_unsupported_and_invalid_references_are_rejected(db_session: AsyncSession, test_user: User, test_workspace: Workspace):
    session = await make_session(db_session, test_workspace, test_user)
    unsupported = await validate_claim_proposal(db_session, session.id, [], [])
    missing_evidence = await validate_claim_proposal(db_session, session.id, [str(uuid.uuid4())], [])
    missing_calculation = await validate_claim_proposal(db_session, session.id, [], [str(uuid.uuid4())])
    assert not unsupported.valid and "UNSUPPORTED_CLAIM" in unsupported.errors
    assert not missing_evidence.valid and any("EVIDENCE_NOT_FOUND" in e for e in missing_evidence.errors)
    assert not missing_calculation.valid and any("CALCULATION_NOT_FOUND" in e for e in missing_calculation.errors)


@pytest.mark.asyncio
async def test_cross_workspace_evidence_is_rejected(db_session: AsyncSession, test_user: User, test_workspace: Workspace):
    other = Workspace(name="Other", created_by=test_user.id)
    db_session.add(other)
    await db_session.flush()
    session = await make_session(db_session, test_workspace, test_user)
    foreign_session = await make_session(db_session, other, test_user)
    evidence = await make_evidence(db_session, foreign_session, other)
    result = await validate_claim_proposal(db_session, session.id, [str(evidence.id)], [])
    assert not result.valid
    assert any("CROSS_INVESTIGATION" in e or "CROSS_WORKSPACE" in e for e in result.errors)


@pytest.mark.asyncio
async def test_multiple_calculations_resolve_by_exact_id(db_session: AsyncSession, test_user: User, test_workspace: Workspace):
    session = await make_session(db_session, test_workspace, test_user)
    evidence = await make_evidence(db_session, session, test_workspace)
    calculations = []
    for name, output in [("revenue", 100), ("cost", 60), ("profit", 40), ("margin", 0.4)]:
        calculation = CalculationRecord(session_id=session.id, calculation_type="test", formula_or_code=name, input_values={"name": name}, computed_output=output, reproducibility_hash=(name * 64)[:64], evidence_ids=[str(evidence.id)])
        db_session.add(calculation)
        calculations.append(calculation)
    await db_session.flush()
    for calculation in calculations:
        result = await validate_claim_proposal(db_session, session.id, [], [str(calculation.id)])
        assert result.valid
        db_session.add(VerifiedClaim(
            session_id=session.id, claim_id_code=f"CLM-{calculation.formula_or_code.upper()}",
            statement=f"{calculation.formula_or_code}={calculation.computed_output}", epistemic_type="calculation",
            calculation_id=calculation.id, calculation_ids=[str(calculation.id)],
            verification_status="VERIFIED", verification_errors=[],
        ))
    await db_session.flush()
    from sqlalchemy import select
    persisted = (await db_session.execute(select(VerifiedClaim).where(VerifiedClaim.session_id == session.id))).scalars().all()
    assert {claim.claim_id_code: claim.calculation_ids[0] for claim in persisted} == {
        f"CLM-{calculation.formula_or_code.upper()}": str(calculation.id) for calculation in calculations
    }
    assert len({str(c.id) for c in calculations}) == 4


@pytest.mark.asyncio
async def test_unsupported_recommendation_is_rejected(db_session: AsyncSession, test_user: User, test_workspace: Workspace):
    session = await make_session(db_session, test_workspace, test_user)
    result = await validate_supporting_claims(db_session, session.id, ["CLM-MISSING"])
    assert not result.valid


@pytest.mark.asyncio
async def test_provider_failure_has_explicit_state(monkeypatch):
    client = OmniOpsLLMClient()
    async def fail(*args):
        raise TimeoutError("provider timed out")
    client._provider.generate_investigation_plan = fail
    with pytest.raises(ProviderError) as exc:
        await client.generate_investigation_plan("objective", {"tables": []})
    assert exc.value.state == ProviderState.TIMEOUT
    assert "stopped" in str(exc.value).lower()


def test_audio_unavailable_has_no_transcript(tmp_path, monkeypatch):
    from app.ingestion import audio_parser
    monkeypatch.setattr(audio_parser.settings, "OPENAI_API_KEY", None)
    path = tmp_path / "recording.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    result = parse_audio_recording(str(path))
    assert result["status"] == "TRANSCRIPTION_UNAVAILABLE"
    assert result["chunks"] == []


def test_image_without_vision_has_only_deterministic_metadata(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 320, 240) + b"\x00" * 16)
    result = parse_image_file(str(path))
    assert result["status"] == "VISION_ANALYSIS_UNAVAILABLE"
    assert result["chunks"] == []
    assert result["metadata"]["width"] == 320
    assert result["metadata"]["height"] == 240
