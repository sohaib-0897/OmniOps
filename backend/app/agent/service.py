"""Single production entry point for durable investigation execution."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.persistence import finalize_synthesis, persist_claim
from app.agent.runtime import (
    DurablePlanExecutor,
    PlanSpec,
    PlanStepSpec,
    RuntimeBudget,
    RuntimeErrorCode,
    ToolDefinition,
    ToolRegistry,
    acquire_lease,
    claim_next_investigation,
    logical_identity,
    owns_lease,
    persist_runtime_event,
    publish_persisted_runtime_events,
    prepare_claimed_investigation_for_recovery,
    release_lease,
    SimulatedWorkerCrash,
    transition,
)
from app.evidence.validator import (
    validate_claim_proposal,
    validate_recommendation_support,
    validate_supporting_claims,
)
from app.models.document import DocumentChunk, ProcessingStatus, SourceDocument, TabularDataset
from app.models.evidence import (
    CalculationRecord,
    ContradictionRecord,
    EvidenceItem,
    InferenceRecord,
    RecommendationRecord,
)
from app.models.investigation import AgentObservation, InvestigationSession, InvestigationStatus, RuntimeState
from app.rag.hybrid_search import HybridRetriever


class RetrievalInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class TabularSQLInput(BaseModel):
    sql_query: str = Field(min_length=1, max_length=20_000)


class PythonCalculationInput(BaseModel):
    code: str = Field(min_length=1, max_length=256 * 1024)
    input_data: Dict[str, Any] = Field(default_factory=dict)


class WebRetrievalInput(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class InvestigationRuntime:
    """Authoritative provider-planned, registry-dispatched durable runtime."""

    def __init__(
        self,
        db: AsyncSession,
        registry: ToolRegistry | None = None,
        budget: RuntimeBudget | None = None,
        llm_client: Any | None = None,
    ):
        self.db = db
        self.production_default = registry is None
        self.registry = registry or self._default_registry()
        self.budget = budget or RuntimeBudget()
        self._llm_client = llm_client

    def _default_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="hybrid_document_search",
            description="Tenant-filtered PostgreSQL hybrid document retrieval.",
            input_model=RetrievalInput,
            execute=self._retrieve,
            timeout_seconds=30,
            max_attempts=2,
            retryable_errors=("TIMEOUT", "CONNECTION"),
        ))
        registry.register(ToolDefinition(
            name="tabular_sql_query",
            description="Read-only DuckDB SQL over registered workspace tables.",
            input_model=TabularSQLInput,
            execute=self._tabular_sql,
            timeout_seconds=30,
            max_attempts=1,
        ))
        registry.register(ToolDefinition(
            name="sandboxed_python_exec",
            description="Isolated deterministic Python calculation.",
            input_model=PythonCalculationInput,
            execute=self._python_calculation,
            timeout_seconds=65,
            max_attempts=1,
        ))
        registry.register(ToolDefinition(
            name="safe_web_retrieval",
            description="SSRF-safe public web extraction persisted as untrusted source data.",
            input_model=WebRetrievalInput,
            execute=self._web_retrieval,
            timeout_seconds=30,
            max_attempts=1,
        ))
        return registry

    @property
    def llm_client(self):
        if self._llm_client is None:
            from app.llm.client import OmniOpsLLMClient
            self._llm_client = OmniOpsLLMClient()
        return self._llm_client

    async def _retrieve(self, context: Dict[str, Any], input: RetrievalInput) -> Dict[str, Any]:
        result = await HybridRetriever.search(
            workspace_id=context["workspace_id"], query=input.query,
            db=context["db"], top_k=input.top_k,
        )
        payload = result.model_dump()
        payload["evidence"] = [{
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "exact_quote": item.content,
            "page_number": item.page_number,
            "cell_range": item.cell_range,
            "audio_start_ms": item.audio_start_ms,
            "audio_end_ms": item.audio_end_ms,
            "locator": {
                "page_number": item.page_number, "cell_range": item.cell_range,
                "audio_start_ms": item.audio_start_ms, "audio_end_ms": item.audio_end_ms,
            },
            "confidence_score": None,
        } for item in result.results]
        return payload

    async def _tabular_sql(self, context: Dict[str, Any], input: TabularSQLInput) -> Dict[str, Any]:
        from app.tools.duckdb_tool import DuckDBTool
        tables = (await context["db"].execute(
            select(TabularDataset).where(TabularDataset.workspace_id == context["workspace_id"])
        )).scalars().all()
        result = DuckDBTool({row.table_name: row.parquet_storage_path for row in tables}).execute_query(
            input.sql_query, max_rows=200,
        )
        if not result.success:
            raise RuntimeError(result.error_message or "TABULAR_QUERY_FAILED")
        return {
            "rows": result.data or [], "columns": result.columns or [],
            "calculations": [{
                "formula": input.sql_query, "inputs": {"max_rows": 200},
                "calculation_type": "sql_query", "computed_output": result.data or [],
                "reproducibility_hash": result.reproducibility_hash,
                "evidence_ids": [], "source_ids": [str(row.source_id) for row in tables],
            }],
        }

    async def _python_calculation(self, context: Dict[str, Any], input: PythonCalculationInput) -> Dict[str, Any]:
        from app.tools.python_sandbox import PythonSandboxRunner
        result = PythonSandboxRunner.execute(input.code, input.input_data)
        if not result.success:
            raise RuntimeError(result.error_code or "SANDBOX_EXECUTION_FAILED")
        evidence = (await context["db"].execute(
            select(EvidenceItem).where(EvidenceItem.session_id == context["investigation_id"])
        )).scalars().all()
        return {
            "result": result.computed_output,
            "calculations": [{
                "formula": input.code, "inputs": input.input_data,
                "calculation_type": "python_math", "computed_output": result.computed_output,
                "reproducibility_hash": result.reproducibility_hash,
                "evidence_ids": [str(row.id) for row in evidence],
                "source_ids": list(dict.fromkeys(str(row.source_id) for row in evidence)),
            }],
        }

    async def _web_retrieval(self, context: Dict[str, Any], input: WebRetrievalInput) -> Dict[str, Any]:
        from app.ingestion.contracts import stable_extraction_id
        from app.ingestion.web_fetcher import fetch_web_page_content
        fetched = await fetch_web_page_content(input.url)
        content = str(fetched.get("content") or "").strip()
        if not content:
            raise RuntimeError("WEB_TEXT_EXTRACTION_UNAVAILABLE")
        digest = hashlib.sha256((str(fetched["url"]) + "\n" + content).encode("utf-8")).hexdigest()
        source = (await context["db"].execute(select(SourceDocument).where(
            SourceDocument.workspace_id == context["workspace_id"], SourceDocument.sha256_hash == digest,
        ))).scalar_one_or_none()
        if source is None:
            source = SourceDocument(
                workspace_id=context["workspace_id"], file_name=str(fetched.get("title") or "Web page")[:255],
                storage_path=f"web:{fetched['url']}", mime_type="text/html",
                byte_size=len(content.encode("utf-8")), sha256_hash=digest, modality="web",
                processing_status=ProcessingStatus.READY.value,
                doc_metadata={"url": fetched["url"], "content_label": "UNTRUSTED_WEB_DATA"},
            )
            context["db"].add(source); await context["db"].flush()
        chunk = (await context["db"].execute(select(DocumentChunk).where(
            DocumentChunk.source_id == source.id, DocumentChunk.chunk_index == 0,
        ))).scalar_one_or_none()
        if chunk is None:
            chunk = DocumentChunk(
                workspace_id=context["workspace_id"], source_id=source.id, chunk_index=0,
                content=content, modality="web", extraction_method="WEB_EXTRACTION",
                lexical_search_status="READY", semantic_search_status="UNAVAILABLE",
                chunk_metadata={
                    "url": fetched["url"], "content_label": "UNTRUSTED_WEB_DATA",
                    "extraction_id": stable_extraction_id(
                        source_hash=digest, modality="web", method="WEB_EXTRACTION",
                        locator={"url": fetched["url"]}, content=content,
                    ),
                },
            )
            context["db"].add(chunk); await context["db"].flush()
        return {
            "url": fetched["url"], "content_label": "UNTRUSTED_WEB_DATA",
            "results": [{"content": content, "source_id": str(source.id), "chunk_id": str(chunk.id)}],
            "evidence": [{
                "source_id": str(source.id), "chunk_id": str(chunk.id),
                "exact_quote": content, "locator": {"url": fetched["url"]},
                "confidence_score": None,
            }],
        }

    async def _catalog_summary(self, investigation: InvestigationSession) -> Dict[str, Any]:
        sources = (await self.db.execute(select(SourceDocument).where(
            SourceDocument.workspace_id == investigation.workspace_id
        ))).scalars().all()
        tables = (await self.db.execute(select(TabularDataset).where(
            TabularDataset.workspace_id == investigation.workspace_id
        ))).scalars().all()
        return {
            "documents": [{
                "id": str(row.id), "name": row.file_name, "modality": row.modality,
                "processing_status": row.processing_status,
            } for row in sources],
            "tables": [{
                "id": str(row.id), "name": row.table_name, "row_count": row.row_count,
                "schema": row.schema_definition,
            } for row in tables],
        }

    async def _provider_plan(self, investigation: InvestigationSession) -> PlanSpec:
        output = await self.llm_client.generate_investigation_plan(
            investigation.objective, await self._catalog_summary(investigation),
        )
        if not output.tasks:
            raise RuntimeError(RuntimeErrorCode.INVALID_PROVIDER_OUTPUT.value)
        available = [{
            "name": name, "description": self.registry.get(name).description,
            "input_schema": self.registry.get(name).input_model.model_json_schema(),
        } for name in self.registry.names()]
        steps: list[PlanStepSpec] = []
        for task in output.tasks[: investigation.max_steps]:
            decision = await self.llm_client.decide_next_action(
                investigation.objective, task, [], available,
            )
            if decision.tool_name not in self.registry.names():
                raise RuntimeError(RuntimeErrorCode.INVALID_PROVIDER_OUTPUT.value)
            steps.append(PlanStepSpec(
                step_id=task.id, objective=task.description, tool_name=decision.tool_name,
                inputs=decision.arguments, expected_evidence_type=task.expected_output,
                completion_criteria={"evidence_required": decision.tool_name in {
                    "hybrid_document_search", "safe_web_retrieval",
                }},
            ))
        if not steps:
            raise RuntimeError(RuntimeErrorCode.INVALID_PROVIDER_OUTPUT.value)
        return PlanSpec(objective=investigation.objective, steps=steps)

    async def _synthesize(self, investigation: InvestigationSession) -> Dict[str, Any]:
        evidence_rows = (await self.db.execute(
            select(EvidenceItem, DocumentChunk, SourceDocument)
            .join(DocumentChunk, EvidenceItem.chunk_id == DocumentChunk.id)
            .join(SourceDocument, EvidenceItem.source_id == SourceDocument.id)
            .where(EvidenceItem.session_id == investigation.id)
        )).all()
        calculations = (await self.db.execute(select(CalculationRecord).where(
            CalculationRecord.session_id == investigation.id
        ))).scalars().all()
        observations = (await self.db.execute(select(AgentObservation).where(
            AgentObservation.investigation_id == investigation.id
        ))).scalars().all()
        evidence_payload = [{
            "id": str(evidence.id), "source_id": str(source.id), "source_name": source.file_name,
            "modality": chunk.modality, "exact_quote": evidence.exact_quote,
            "page_number": evidence.page_number, "cell_range": evidence.cell_range,
            "audio_start_ms": evidence.audio_start_ms, "audio_end_ms": evidence.audio_end_ms,
        } for evidence, chunk, source in evidence_rows]
        calculation_payload = [{
            "id": str(row.id), "calculation_type": row.calculation_type,
            "formula_or_code": row.formula_or_code, "input_values": row.input_values,
            "computed_output": row.computed_output, "reproducibility_hash": row.reproducibility_hash,
        } for row in calculations]
        proposal = await self.llm_client.verify_and_synthesize(
            investigation.objective,
            [{"classification": row.classification, "success": row.success, "summary": row.summary} for row in observations],
            evidence_payload, calculation_payload,
        )

        report_claims: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for claim in proposal.claims:
            validation = await validate_claim_proposal(
                self.db, investigation.id, claim.citations, claim.calculation_ids,
            )
            persisted = await persist_claim(
                self.db, session_id=investigation.id,
                step_id=f"synthesis:{investigation.plan_version}", statement=claim.statement,
                lineage={"evidence_ids": claim.citations, "calculation_ids": claim.calculation_ids},
                claim_id_code=claim.claim_id, epistemic_type=claim.epistemic_type,
                confidence_score=claim.confidence_score, supporting_citations=claim.citations,
                calculation_ids=claim.calculation_ids, supporting_claims=claim.supporting_claims,
                verification_status="VERIFIED" if validation.valid else "REJECTED",
                verification_errors=validation.errors,
            )
            item = {
                "claim_id": persisted.claim_id_code, "statement": persisted.statement,
                "epistemic_type": persisted.epistemic_type, "confidence_score": persisted.confidence_score,
                "citations": persisted.supporting_citations, "calculation_ids": persisted.calculation_ids,
                "calculation_summary": claim.calculation_summary,
                "supporting_claims": persisted.supporting_claims,
                "verification_status": persisted.verification_status,
                "verification_errors": persisted.verification_errors,
            }
            (report_claims if validation.valid else rejected).append(item)
        if not report_claims:
            raise RuntimeError(RuntimeErrorCode.EVIDENCE_INVALID.value)

        report_inferences: list[dict[str, Any]] = []
        for item in proposal.inferences:
            validation = await validate_supporting_claims(self.db, investigation.id, item.supporting_claim_ids)
            record = (await self.db.execute(select(InferenceRecord).where(
                InferenceRecord.session_id == investigation.id,
                InferenceRecord.inference_id_code == item.inference_id,
            ))).scalar_one_or_none()
            if record is None:
                record = InferenceRecord(
                    session_id=investigation.id, inference_id_code=item.inference_id,
                    statement=item.statement, supporting_claim_ids=item.supporting_claim_ids,
                    verification_status="VERIFIED" if validation.valid else "REJECTED",
                    verification_errors=validation.errors,
                )
                self.db.add(record)
            value = {
                "inference_id": item.inference_id, "statement": item.statement,
                "supporting_claim_ids": item.supporting_claim_ids,
                "verification_status": record.verification_status,
                "verification_errors": record.verification_errors,
            }
            (report_inferences if validation.valid else rejected).append(value)

        report_recommendations: list[dict[str, Any]] = []
        for item in proposal.recommendations:
            validation = await validate_recommendation_support(
                self.db, investigation.id, item.supported_by_claims, item.supporting_inference_ids,
            )
            record = (await self.db.execute(select(RecommendationRecord).where(
                RecommendationRecord.session_id == investigation.id,
                RecommendationRecord.recommendation_id_code == item.recommendation_id,
            ))).scalar_one_or_none()
            if record is None:
                record = RecommendationRecord(
                    session_id=investigation.id, recommendation_id_code=item.recommendation_id,
                    statement=item.action, priority=item.priority,
                    supporting_claim_ids=item.supported_by_claims,
                    supporting_inference_ids=item.supporting_inference_ids,
                    verification_status="VERIFIED" if validation.valid else "REJECTED",
                    verification_errors=validation.errors,
                )
                self.db.add(record)
            value = {
                "recommendation_id": item.recommendation_id, "title": item.title,
                "action": item.action, "priority": item.priority,
                "supported_by_claims": item.supported_by_claims,
                "supporting_inference_ids": item.supporting_inference_ids,
                "verification_status": record.verification_status,
                "verification_errors": record.verification_errors,
            }
            (report_recommendations if validation.valid else rejected).append(value)

        verified_codes = {item["claim_id"] for item in report_claims}
        contradictions = (await self.db.execute(select(ContradictionRecord).where(
            ContradictionRecord.investigation_id == investigation.id,
            ContradictionRecord.status == "UNRESOLVED",
        ))).scalars().all()
        return {
            "executive_summary": proposal.executive_summary,
            "key_findings": [item for item in proposal.key_findings
                             if not item.get("claim_id") or item.get("claim_id") in verified_codes],
            "claims": report_claims, "inferences": report_inferences,
            "recommendations": report_recommendations, "rejected_proposals": rejected,
            "missing_data_warnings": proposal.missing_data_warnings,
            "contradictions": [row.topic for row in contradictions],
            "provider": self.llm_client.provenance(),
        }

    async def execute_claimed(self, investigation: InvestigationSession, worker_id: str | None = None) -> Dict[str, Any]:
        if RuntimeState(investigation.current_state) in {
            RuntimeState.COMPLETED, RuntimeState.CANCELLED, RuntimeState.FAILED,
        }:
            return {"status": investigation.current_state}
        try:
            if self.production_default and RuntimeState(investigation.current_state) == RuntimeState.SYNTHESIZING:
                result = {"status": "completed", "outputs": {}}
            else:
                if self.production_default:
                    if RuntimeState(investigation.current_state) == RuntimeState.CREATED:
                        await transition(self.db, investigation, RuntimeState.PLANNING, "provider_planning")
                    plan = await self._provider_plan(investigation)
                else:
                    plan = PlanSpec(objective=investigation.objective, steps=[PlanStepSpec(
                        step_id="retrieval-1", objective=investigation.objective,
                        tool_name="hybrid_document_search", expected_evidence_type="document_chunk",
                        completion_criteria={"evidence_required": True},
                        inputs={"query": investigation.objective, "top_k": 5},
                    )])
                result = await DurablePlanExecutor(self.db, self.registry, self.budget).execute(
                    investigation, plan,
                    context={
                        "db": self.db, "workspace_id": investigation.workspace_id,
                        "investigation_id": investigation.id,
                        "worker_id": worker_id if self.db.get_bind().dialect.name != "sqlite" else None,
                        "defer_synthesis": self.production_default,
                    },
                )

            if result.get("status") == "completed":
                if worker_id and self.db.get_bind().dialect.name != "sqlite" and not await owns_lease(
                    self.db, investigation.id, worker_id,
                ):
                    raise RuntimeError(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
                await persist_runtime_event(
                    self.db, investigation.id, "synthesis.started",
                    logical_identity(investigation.id, "synthesis.started", investigation.plan_version),
                    {"plan_version": investigation.plan_version},
                )
                report = await self._synthesize(investigation) if self.production_default else {
                    "executive_summary": "Injected deterministic runtime completed.",
                    "key_findings": [], "claims": [], "inferences": [], "recommendations": [],
                    "rejected_proposals": [], "missing_data_warnings": [], "contradictions": [],
                    "outputs": result.get("outputs", {}),
                }
                await finalize_synthesis(
                    self.db, investigation, report, investigation.plan_version,
                    worker_id=worker_id if self.db.get_bind().dialect.name != "sqlite" else None,
                )
                if RuntimeState(investigation.current_state) == RuntimeState.SYNTHESIZING:
                    await transition(self.db, investigation, RuntimeState.COMPLETED, "synthesis_validated")
                investigation.status = InvestigationStatus.COMPLETED.value
                await persist_runtime_event(
                    self.db, investigation.id, "synthesis.completed",
                    logical_identity(investigation.id, "synthesis.completed", investigation.plan_version),
                    {"plan_version": investigation.plan_version},
                )
                await persist_runtime_event(
                    self.db, investigation.id, "investigation.completed",
                    logical_identity(investigation.id, "investigation.completed", investigation.plan_version),
                    {"plan_version": investigation.plan_version},
                )
            elif result.get("status") == RuntimeState.CANCELLED.value:
                investigation.status = InvestigationStatus.CANCELLED.value
            await self.db.commit(); await publish_persisted_runtime_events(self.db)
            return result
        except SimulatedWorkerCrash:
            raise
        except Exception as exc:
            if worker_id and self.db.get_bind().dialect.name != "sqlite" and not await owns_lease(
                self.db, investigation.id, worker_id,
            ):
                await self.db.rollback()
                return {"status": RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value}
            if RuntimeState(investigation.current_state) not in {
                RuntimeState.COMPLETED, RuntimeState.CANCELLED, RuntimeState.FAILED,
            }:
                investigation.current_state = RuntimeState.FAILED.value
                investigation.completed_at = datetime.now(timezone.utc)
            investigation.status = InvestigationStatus.FAILED.value
            investigation.failure_code = getattr(exc, "code", None) or str(exc).split(":", 1)[0] or "INVESTIGATION_FAILED"
            investigation.failure_message = "Durable runtime could not complete the investigation."
            await persist_runtime_event(
                self.db, investigation.id, "investigation.failed",
                logical_identity(investigation.id, "investigation.failed", investigation.plan_version),
                {"code": investigation.failure_code},
            )
            await self.db.commit(); await publish_persisted_runtime_events(self.db)
            return {"status": RuntimeState.FAILED.value, "error_code": investigation.failure_code}

    async def run_worker_once(self, worker_id: str) -> Optional[Dict[str, Any]]:
        investigation = await claim_next_investigation(self.db, worker_id)
        if investigation is None:
            return None
        try:
            await prepare_claimed_investigation_for_recovery(self.db, investigation)
            return await self.execute_claimed(investigation, worker_id)
        finally:
            await release_lease(self.db, investigation, worker_id)
            await self.db.commit(); await publish_persisted_runtime_events(self.db)


async def run_investigation(
    session_id: uuid.UUID,
    db: AsyncSession,
    worker_id: str = "api-worker",
    registry=None,
) -> Dict[str, Any]:
    """Service-level entry point used by API, workers, and resume operations."""
    session = (await db.execute(select(InvestigationSession).where(
        InvestigationSession.id == session_id
    ).with_for_update())).scalar_one()
    from app.agent.sse_manager import sse_manager
    if sse_manager.get_cancellation_event(str(session_id)).is_set() or session.cancellation_requested:
        session.cancellation_requested = True
        session.current_state = RuntimeState.CANCELLED.value
        session.status = InvestigationStatus.CANCELLED.value
        session.failure_code = RuntimeErrorCode.CANCELLED.value
        session.completed_at = datetime.now(timezone.utc)
        await db.commit(); await publish_persisted_runtime_events(db)
        return {"status": RuntimeState.CANCELLED.value}
    runtime = InvestigationRuntime(
        db, registry=registry, budget=RuntimeBudget(max_steps=session.max_steps),
    )
    await persist_runtime_event(
        db, session.id, "investigation.started", logical_identity(session.id, "investigation.started"),
        {"worker_id": worker_id},
    )
    if not await acquire_lease(db, session, worker_id):
        return {"status": RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value}
    try:
        return await runtime.execute_claimed(session, worker_id)
    finally:
        await release_lease(db, session, worker_id)
        await db.commit(); await publish_persisted_runtime_events(db)
