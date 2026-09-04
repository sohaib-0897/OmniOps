"""Single production entry point for durable investigation execution."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import (
    DurablePlanExecutor, PlanSpec, PlanStepSpec, RuntimeBudget, RuntimeErrorCode,
    claim_next_investigation, release_lease, acquire_lease, persist_runtime_event, publish_persisted_runtime_events, logical_identity,
)
from app.models.investigation import InvestigationSession, InvestigationStatus, RuntimeState
from app.rag.hybrid_search import HybridRetriever
from app.agent.persistence import finalize_synthesis


class RetrievalInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class InvestigationRuntime:
    """Authoritative runtime; callers never dispatch tools directly."""

    def __init__(self, db: AsyncSession, registry=None, budget: RuntimeBudget = RuntimeBudget()):
        self.db, self.registry, self.budget = db, registry, budget
        if self.registry is None:
            from app.agent.runtime import ToolRegistry, ToolDefinition
            self.registry = ToolRegistry()
            self.registry.register(ToolDefinition(
                name="hybrid_document_search", description="PostgreSQL hybrid retrieval",
                input_model=RetrievalInput, execute=self._retrieve, timeout_seconds=30,
                max_attempts=2, retryable_errors=("TIMEOUT", "CONNECTION"),
            ))

    async def _retrieve(self, context: Dict[str, Any], input: RetrievalInput) -> Dict[str, Any]:
        result = await HybridRetriever.search(workspace_id=context["workspace_id"], query=input.query, db=context["db"], top_k=input.top_k)
        return result.model_dump()

    async def execute_claimed(self, investigation: InvestigationSession, worker_id: str | None = None) -> Dict[str, Any]:
        if RuntimeState(investigation.current_state) in {RuntimeState.COMPLETED, RuntimeState.CANCELLED, RuntimeState.FAILED}:
            return {"status": investigation.current_state}
        plan = PlanSpec(objective=investigation.objective, steps=[PlanStepSpec(
            step_id="retrieval-1", objective=investigation.objective,
            tool_name="hybrid_document_search", expected_evidence_type="document_chunk",
            completion_criteria={"evidence_required": True},
            inputs={"query": investigation.objective, "top_k": 5},
        )])
        try:
            result = await DurablePlanExecutor(self.db, self.registry, self.budget).execute(
            investigation, plan, context={"db": self.db, "workspace_id": investigation.workspace_id, "worker_id": worker_id if self.db.get_bind().dialect.name != "sqlite" else None},
            )
        except Exception as exc:
            investigation.current_state = RuntimeState.FAILED.value
            investigation.status = InvestigationStatus.FAILED.value
            investigation.failure_code = str(exc).split(":", 1)[0]
            investigation.failure_message = "Durable runtime could not complete the investigation."
            await persist_runtime_event(self.db, investigation.id, "investigation.failed", logical_identity(investigation.id, "investigation.failed", investigation.plan_version), {"code": investigation.failure_code})
            await self.db.commit()
            await publish_persisted_runtime_events(self.db)
            return {"status": RuntimeState.FAILED.value, "error_code": investigation.failure_code}
        if result.get("status") == "completed":
            investigation.status = InvestigationStatus.COMPLETED.value
            await persist_runtime_event(self.db, investigation.id, "synthesis.started", logical_identity(investigation.id, "synthesis.started", investigation.plan_version), {"plan_version": investigation.plan_version})
            await finalize_synthesis(self.db, investigation, {"status": "completed", "outputs": result.get("outputs", {})}, investigation.plan_version)
            await persist_runtime_event(self.db, investigation.id, "synthesis.completed", logical_identity(investigation.id, "synthesis.completed", investigation.plan_version), {"plan_version": investigation.plan_version})
            await persist_runtime_event(self.db, investigation.id, "investigation.completed", logical_identity(investigation.id, "investigation.completed", investigation.plan_version), {"plan_version": investigation.plan_version})
        elif result.get("status") == RuntimeState.CANCELLED.value:
            investigation.status = InvestigationStatus.CANCELLED.value
        await self.db.commit()
        await publish_persisted_runtime_events(self.db)
        return result

    async def run_worker_once(self, worker_id: str) -> Optional[Dict[str, Any]]:
        investigation = await claim_next_investigation(self.db, worker_id)
        if investigation is None:
            return None
        try:
            return await self.execute_claimed(investigation, worker_id)
        finally:
            await release_lease(self.db, investigation, worker_id)
            await self.db.commit()
            await publish_persisted_runtime_events(self.db)


async def run_investigation(session_id: uuid.UUID, db: AsyncSession, worker_id: str = "api-worker", registry=None) -> Dict[str, Any]:
    """Service-level entry point used by API, workers, and resume operations."""
    session = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == session_id).with_for_update())).scalar_one()
    from app.agent.sse_manager import sse_manager
    if sse_manager.get_cancellation_event(str(session_id)).is_set() or session.cancellation_requested:
        session.cancellation_requested = True
        session.current_state = RuntimeState.CANCELLED.value
        session.status = InvestigationStatus.CANCELLED.value
        session.failure_code = RuntimeErrorCode.CANCELLED.value
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await publish_persisted_runtime_events(db)
        return {"status": RuntimeState.CANCELLED.value}
    from app.core.config import settings
    if registry is None and not (settings.OPENAI_API_KEY or settings.GEMINI_API_KEY):
        session.current_state = RuntimeState.FAILED.value
        session.status = InvestigationStatus.FAILED.value
        session.failure_code = "LLM_PROVIDER_REQUIRED"
        session.failure_message = "A configured semantic provider is required for production investigation planning."
        session.completed_at = datetime.now(timezone.utc)
        await persist_runtime_event(db, session.id, "investigation.failed", logical_identity(session.id, "investigation.failed", "provider"), {"code": "LLM_PROVIDER_REQUIRED"})
        await db.commit()
        await publish_persisted_runtime_events(db)
        return {"status": RuntimeState.FAILED.value, "error_code": "LLM_PROVIDER_REQUIRED"}
    runtime = InvestigationRuntime(db, registry=registry)
    await persist_runtime_event(db, session.id, "investigation.started", logical_identity(session.id, "investigation.started"), {"worker_id": worker_id})
    from app.agent.sse_manager import sse_manager
    if sse_manager.get_cancellation_event(str(session_id)).is_set():
        session.cancellation_requested = True
    if session.cancellation_requested:
        session.current_state = RuntimeState.CANCELLED.value
        session.status = InvestigationStatus.CANCELLED.value
        session.failure_code = RuntimeErrorCode.CANCELLED.value
        await db.commit()
        await publish_persisted_runtime_events(db)
        return {"status": RuntimeState.CANCELLED.value}
    if not await acquire_lease(db, session, worker_id):
        return {"status": RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value}
    try:
        return await runtime.execute_claimed(session, worker_id)
    finally:
        await release_lease(db, session, worker_id)
        await db.commit()
        await publish_persisted_runtime_events(db)
