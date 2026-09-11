"""Explicit UI QA fixtures in the dedicated closure DB, never provider output.

Uses a real uploaded test excerpt and authored presentation fixtures. A held
lease keeps the active fixture away from provider execution during browser QA.
"""
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from phase6_topology import docker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.models.user import Workspace
from app.models.document import SourceDocument, DocumentChunk
from app.models.investigation import InvestigationSession
from app.models.evidence import RuntimeEvent, EvidenceItem, CalculationRecord, VerifiedClaim, InferenceRecord, RecommendationRecord


async def main():
    config = json.loads(docker("inspect", "omniops-phase6-a"))[0]
    env = dict(item.split("=", 1) for item in config["Config"]["Env"] if "=" in item)
    url = env["DATABASE_URL"].replace("@omniops-postgres:", "@127.0.0.1:")
    assert url.rsplit("/", 1)[-1] == "omniops_phase6_closure_test"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = json.loads((ROOT / ".ui-qa/context.json").read_text())
    workspace_id, user_id = uuid.UUID(context["workspaceId"]), uuid.UUID(context["userId"])
    async with factory() as db:
        workspace = await db.get(Workspace, workspace_id)
        assert workspace.created_by == user_id and "UI QA" in workspace.name
        now = datetime.now(timezone.utc)
        if "--append" in sys.argv:
            ids = json.loads((ROOT / ".ui-qa/fixtures.json").read_text())
            inv = uuid.UUID(ids["activeId"])
            db.add(RuntimeEvent(investigation_id=inv, event_type="tool.completed", logical_identity=f"ui-qa:{inv}:{uuid.uuid4()}", payload={"tool": "ui_qa_fixture", "duration_ms": 40}, created_at=now))
            await db.commit()
            print("UI_QA_PERSISTED_EVENT_APPENDED")
        else:
            source = (await db.execute(select(SourceDocument).where(SourceDocument.workspace_id == workspace_id, SourceDocument.file_name == "operating-review-qa.txt"))).scalars().first()
            assert source and source.processing_status in ("ready", "partially_ready")
            chunk = (await db.execute(select(DocumentChunk).where(DocumentChunk.source_id == source.id))).scalars().first()
            assert chunk and "INTERFACE QA TEST DATA ONLY" in chunk.content
            active = InvestigationSession(workspace_id=workspace_id, user_id=user_id, objective="UI QA fixture: inspect the persisted operational trace", status="running", current_state="executing", worker_id="ui-qa-fixture-holder", lease_acquired_at=now, lease_expires_at=now + timedelta(hours=2))
            report = InvestigationSession(workspace_id=workspace_id, user_id=user_id, objective="UI QA fixture: report and provenance presentation", status="completed", current_state="completed", completed_at=now)
            db.add_all([active, report]); await db.flush()
            for index, (kind, payload) in enumerate([
                ("investigation.created", {"workspace_id": str(workspace_id)}),
                ("state.changed", {"from": "created", "to": "planning"}),
                ("plan_created", {"tasks": [{"id": "qa-task-1", "title": "Inspect uploaded test source", "target_modality": "text", "status": "completed"}, {"id": "qa-task-2", "title": "Verify test references", "target_modality": "text", "status": "in_progress"}]}),
                ("state.changed", {"from": "planning", "to": "executing"}),
                ("tool.started", {"tool": "ui_qa_fixture", "step_id": "qa-step-1", "correlation_id": "ui-qa-correlation"}),
            ]):
                db.add(RuntimeEvent(investigation_id=active.id, event_type=kind, logical_identity=f"ui-qa:{active.id}:{index}", payload=payload, created_at=now + timedelta(milliseconds=index)))
            ev = EvidenceItem(session_id=report.id, source_id=source.id, chunk_id=chunk.id, exact_quote=chunk.content, confidence_score=None, coordinates={"test_fixture": True})
            db.add(ev); await db.flush()
            code = "24 / 7"
            calc = CalculationRecord(session_id=report.id, calculation_type="python_math", formula_or_code=code, input_values={"requests": 24, "days": 7}, computed_output=24 / 7, reproducibility_hash=hashlib.sha256(code.encode()).hexdigest(), evidence_ids=[str(ev.id)], source_ids=[str(source.id)])
            db.add(calc); await db.flush()
            claims = [
                {"claim_id": "QA-F1", "statement": "UI QA fixture: the uploaded test source records 24 resolved requests in a sample week.", "epistemic_type": "fact", "confidence_score": None, "citations": [str(ev.id)], "calculation_ids": [], "supporting_claims": [], "verification_status": "VERIFIED"},
                {"claim_id": "QA-C1", "statement": "UI QA fixture: 24 requests over seven days is approximately 3.4286 requests per day.", "epistemic_type": "calculation", "confidence_score": None, "citations": [str(ev.id)], "calculation_ids": [str(calc.id)], "calculation_summary": code, "supporting_claims": ["QA-F1"], "verification_status": "VERIFIED"},
                {"claim_id": "QA-A1", "statement": "UI QA fixture: a longer reporting period would be representative.", "epistemic_type": "assumption", "confidence_score": None, "citations": [], "calculation_ids": [], "supporting_claims": []},
            ]
            for claim in claims:
                db.add(VerifiedClaim(session_id=report.id, claim_id_code=claim["claim_id"], statement=claim["statement"], epistemic_type=claim["epistemic_type"], confidence_score=None, supporting_citations=claim["citations"], calculation_ids=claim["calculation_ids"], supporting_claims=claim["supporting_claims"], verification_status=claim.get("verification_status", "PROPOSED")))
            inference = "UI QA fixture: this sample alone cannot establish a long-term operating trend."
            recommendation = "Collect a comparable second sample before making an operating decision."
            db.add(InferenceRecord(session_id=report.id, inference_id_code="QA-I1", statement=inference, supporting_claim_ids=["QA-F1"], verification_status="VERIFIED"))
            db.add(RecommendationRecord(session_id=report.id, recommendation_id_code="QA-R1", statement=recommendation, priority="medium", supporting_claim_ids=["QA-F1"], supporting_inference_ids=["QA-I1"], verification_status="VERIFIED"))
            report.final_response = {"executive_summary": "UI QA FIXTURE — not a provider-generated analysis. This authored test report exercises the presentation of recorded claims, calculations, citations, inferences, recommendations, and limitations using an uploaded test source.", "key_findings": [{"title": "Sample operating activity", "detail": "The test source describes one sample week. No production conclusions follow from this fixture.", "claim_id": "QA-F1"}], "claims": claims, "inferences": [{"inference_id": "QA-I1", "statement": inference, "supporting_claim_ids": ["QA-F1"]}], "recommendations": [{"recommendation_id": "QA-R1", "title": "Extend the sample", "action": recommendation, "priority": "medium", "supported_by_claims": ["QA-F1"], "supporting_inference_ids": ["QA-I1"]}], "contradictions": ["UI QA comparison fixture: one source describes a sample week; another reporting period has not been supplied. This text tests the conflict section, not an actual detected conflict."], "missing_data_warnings": ["Authored UI QA fixture. Verification labels are test inputs, not a live verification result.", "No production provider is configured for this local visual test."], "rejected_proposals": []}
            db.add(RuntimeEvent(investigation_id=report.id, event_type="investigation.completed", logical_identity=f"ui-qa:{report.id}:completed", payload={"status": "completed"}, created_at=now))
            await db.commit()
            ids = {"activeId": str(active.id), "reportId": str(report.id), "workspaceId": str(workspace_id), "sourceId": str(source.id), "evidenceId": str(ev.id)}
            (ROOT / ".ui-qa/fixtures.json").write_text(json.dumps(ids))
            print("UI_QA_EXPLICIT_FIXTURES_READY")
    await engine.dispose()


asyncio.run(main())
