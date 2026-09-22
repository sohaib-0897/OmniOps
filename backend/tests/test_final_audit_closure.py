import re
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agent.persistence import (
    invalidate_source_dependents,
    persist_calculation,
    persist_claim,
)
from app.agent.service import InvestigationRuntime
from app.evidence.calculation_identity import calculation_reproducibility_hash
from app.evidence.validator import validate_claim_proposal
from app.llm.base import (
    EpistemicClaim,
    PlanOutput,
    PlannedTask,
    SynthesisReport,
    ToolDecision,
)
from app.models.document import DocumentChunk, ProcessingStatus, SourceDocument
from app.models.evidence import CalculationRecord, EvidenceItem, VerifiedClaim
from app.models.investigation import InvestigationSession, RuntimeState
from app.rag.hybrid_search import HybridSearchResponse, RetrievedChunk


class FakeProviderClient:
    def __init__(self):
        self.calls: list[str] = []

    async def generate_investigation_plan(self, objective, catalog_summary):
        self.calls.append("plan")
        return PlanOutput(
            reasoning_summary="test provider plan",
            tasks=[PlannedTask(
                id="source-search", title="Find evidence",
                description="Find authoritative revenue evidence.",
                target_modality="document", expected_output="A cited source excerpt.",
            )],
        )

    async def decide_next_action(self, objective, current_task, prior_observations, available_tools):
        self.calls.append("decide")
        assert "hybrid_document_search" in {tool["name"] for tool in available_tools}
        return ToolDecision(
            tool_name="hybrid_document_search",
            arguments={"query": "revenue", "top_k": 1},
            user_activity_summary="Searching documents.",
        )

    async def verify_and_synthesize(self, objective, observations, evidence_items, calculations):
        self.calls.append("synthesize")
        assert len(evidence_items) == 1
        evidence_id = evidence_items[0]["id"]
        return SynthesisReport(
            executive_summary="Revenue was 42 million.",
            key_findings=[{"title": "Audited revenue", "detail": "42 million", "claim_id": "CLM-001"}],
            claims=[EpistemicClaim(
                claim_id="CLM-001", statement="Revenue was 42 million.",
                epistemic_type="fact", confidence_score=0.9,
                citations=[evidence_id],
            )],
            recommendations=[],
        )

    def provenance(self):
        return {"provider": "FakeProviderClient", "state": "AVAILABLE"}


@pytest.mark.asyncio
async def test_default_runtime_uses_provider_plan_tools_and_grounded_synthesis(
    db_session, test_user, test_workspace, monkeypatch,
):
    source = SourceDocument(
        workspace_id=test_workspace.id, file_name="revenue.txt", storage_path="revenue.txt",
        mime_type="text/plain", byte_size=32, sha256_hash="a" * 64,
        modality="text", processing_status=ProcessingStatus.READY.value,
    )
    db_session.add(source)
    await db_session.flush()
    chunk = DocumentChunk(
        workspace_id=test_workspace.id, source_id=source.id, chunk_index=0,
        content="Audited revenue was 42 million.", modality="text",
        extraction_method="UTF8_TEXT", lexical_search_status="READY",
        semantic_search_status="UNAVAILABLE",
    )
    db_session.add(chunk)
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id,
        objective="What was audited revenue?",
    )
    db_session.add(investigation)
    await db_session.commit()

    async def fake_search(**kwargs):
        return HybridSearchResponse(
            mode="LEXICAL_ONLY", backend="POSTGRESQL_PGVECTOR_FTS_RRF", rrf_k=60,
            semantic_state="UNAVAILABLE", lexical_state="READY",
            results=[RetrievedChunk(
                chunk_id=str(chunk.id), source_id=str(source.id), source_name=source.file_name,
                modality="text", content=chunk.content, lexical_rank=1,
                lexical_score=1.0, fused_score=1 / 61,
            )],
        )

    monkeypatch.setattr("app.agent.service.HybridRetriever.search", fake_search)
    provider = FakeProviderClient()
    result = await InvestigationRuntime(db_session, llm_client=provider).execute_claimed(investigation)
    await db_session.refresh(investigation)

    claim = (await db_session.execute(select(VerifiedClaim).where(
        VerifiedClaim.session_id == investigation.id,
    ))).scalar_one()
    assert result["status"] == "completed"
    assert provider.calls == ["plan", "decide", "synthesize"]
    assert investigation.current_state == RuntimeState.COMPLETED.value
    assert investigation.final_response["claims"][0]["verification_status"] == "VERIFIED"
    assert claim.verification_status == "VERIFIED"
    # The persisted report must carry the canonical frontend key-finding shape.
    finding = investigation.final_response["key_findings"][0]
    assert set(finding) == {"title", "detail", "claim_id"}
    assert finding["detail"] == "42 million"


@pytest.mark.asyncio
async def test_calculation_hash_is_canonical_and_nested_lineage_is_checked(
    db_session, test_user, test_workspace,
):
    other_source = SourceDocument(
        workspace_id=test_workspace.id, file_name="other.txt", storage_path="other.txt",
        mime_type="text/plain", byte_size=5, sha256_hash="b" * 64,
        modality="text", processing_status=ProcessingStatus.READY.value,
    )
    actual_source = SourceDocument(
        workspace_id=test_workspace.id, file_name="actual.txt", storage_path="actual.txt",
        mime_type="text/plain", byte_size=5, sha256_hash="c" * 64,
        modality="text", processing_status=ProcessingStatus.READY.value,
    )
    db_session.add_all([other_source, actual_source])
    await db_session.flush()
    chunk = DocumentChunk(
        workspace_id=test_workspace.id, source_id=actual_source.id, chunk_index=0,
        content="value is five", modality="text", extraction_method="UTF8_TEXT",
    )
    db_session.add(chunk)
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id, objective="calculate",
    )
    db_session.add(investigation)
    await db_session.flush()
    broken = EvidenceItem(
        session_id=investigation.id, source_id=other_source.id, chunk_id=chunk.id,
        exact_quote="value is five",
    )
    db_session.add(broken)
    await db_session.flush()
    calculation = await persist_calculation(
        db_session, session_id=investigation.id, step_id="calc", formula="x + y",
        inputs={"y": 3, "x": 2}, calculation_type="python_math",
        computed_output={"total": 5}, reproducibility_hash="bogus",
        evidence_ids=[str(broken.id)], source_ids=[str(other_source.id)],
    )
    await db_session.flush()

    assert calculation.reproducibility_hash == calculation_reproducibility_hash(
        "x + y", {"x": 2, "y": 3}, {"total": 5},
    )
    validation = await validate_claim_proposal(
        db_session, investigation.id, [], [str(calculation.id)],
    )
    assert not validation.valid
    assert any("BROKEN_EVIDENCE_SOURCE_CHAIN" in error for error in validation.errors)


@pytest.mark.asyncio
async def test_source_invalidation_revokes_persisted_claim_and_report(
    db_session, test_user, test_workspace,
):
    source = SourceDocument(
        workspace_id=test_workspace.id, file_name="source.txt", storage_path="source.txt",
        mime_type="text/plain", byte_size=8, sha256_hash="d" * 64,
        modality="text", processing_status=ProcessingStatus.READY.value,
    )
    db_session.add(source)
    await db_session.flush()
    chunk = DocumentChunk(
        workspace_id=test_workspace.id, source_id=source.id, chunk_index=0,
        content="ground truth", modality="text", extraction_method="UTF8_TEXT",
    )
    db_session.add(chunk)
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id, objective="grounded",
    )
    db_session.add(investigation)
    await db_session.flush()
    evidence = EvidenceItem(
        session_id=investigation.id, source_id=source.id, chunk_id=chunk.id,
        exact_quote="ground truth",
    )
    db_session.add(evidence)
    await db_session.flush()
    claim = await persist_claim(
        db_session, session_id=investigation.id, step_id="synthesis",
        statement="The source states ground truth.", lineage={"evidence_ids": [str(evidence.id)]},
        claim_id_code="CLM-DELETE", supporting_citations=[str(evidence.id)],
        verification_status="VERIFIED", verification_errors=[],
    )
    investigation.final_response = {
        "claims": [{"claim_id": "CLM-DELETE", "verification_status": "VERIFIED"}],
        "missing_data_warnings": [],
    }
    await invalidate_source_dependents(db_session, source_id=source.id)
    await db_session.flush()

    assert claim.verification_status == "REJECTED"
    assert "SOURCE_DELETED" in claim.verification_errors
    assert investigation.final_response["claims"][0]["verification_status"] == "REJECTED"
    assert investigation.final_response["missing_data_warnings"]


def test_sandbox_runner_health_requires_runner_secret(monkeypatch):
    from app import sandbox_runner_server

    monkeypatch.setattr(sandbox_runner_server.RunnerSettings, "token", "test-runner-secret")
    with pytest.raises(HTTPException) as error:
        sandbox_runner_server.health(None)
    assert error.value.status_code == 401
    assert sandbox_runner_server.health("Bearer test-runner-secret") == {"status": "ok"}


def test_production_worker_has_provider_egress_without_exposing_runner_network():
    compose = (
        Path(__file__).resolve().parents[2] / "docker-compose.ubuntu.yml"
    ).read_text(encoding="utf-8")

    worker = re.search(r"(?ms)^  worker:\n(.*?)(?=^  frontend:)", compose)
    runner = re.search(r"(?ms)^  sandbox-runner:\n(.*?)(?=^  caddy:)", compose)

    assert worker is not None
    assert "networks: [data, runner, egress]" in worker.group(1)
    assert 'extra_hosts: ["host.docker.internal:host-gateway"]' in worker.group(1)
    assert "OLLAMA_BASE_URL:" in compose
    assert runner is not None
    assert "networks: [runner]" in runner.group(1)
    assert "host.docker.internal" not in runner.group(1)
    assert re.search(r"(?m)^  egress:\s*$", compose)
    assert re.search(r"(?ms)^  data:\n    internal: true", compose)
    assert re.search(r"(?ms)^  runner:\n    internal: true", compose)


@pytest.mark.asyncio
async def test_unmatched_metric_route_label_is_bounded(client):
    from app.core.observability import prometheus_metrics

    random_path = f"/attacker-{uuid.uuid4()}"
    assert (await client.get(random_path)).status_code == 404
    metrics = prometheus_metrics()
    assert random_path not in metrics
    assert 'route="__unmatched__"' in metrics
