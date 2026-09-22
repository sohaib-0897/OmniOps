"""Durable, bounded primitives for the Phase 3 agent runtime."""
from __future__ import annotations

import asyncio
import inspect
import re
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Type
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy import update, select, func

from app.models.investigation import (
    AgentObservation, AgentPlan, AgentPlanStep, AgentToolAttempt, AgentTransition, InvestigationSession, RuntimeState,
)
from app.models.evidence import ContradictionRecord, RuntimeEvent, EvidenceItem, CalculationRecord, VerifiedClaim


class RuntimeErrorCode(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    PLAN_INVALID = "PLAN_INVALID"
    PLAN_CYCLE = "PLAN_CYCLE"
    REPLAN_EXHAUSTED = "REPLAN_EXHAUSTED"
    STEP_ATTEMPTS_EXHAUSTED = "STEP_ATTEMPTS_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CANCELLED = "CANCELLED"
    UNSUPPORTED_OBJECTIVE = "UNSUPPORTED_OBJECTIVE"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"
    WORKER_LEASE_UNAVAILABLE = "WORKER_LEASE_UNAVAILABLE"


class SimulatedWorkerCrash(BaseException):
    """Deterministic test seam for a worker dying before result commit."""


class WorkerLeaseLost(RuntimeError):
    """Raised before a stale worker can mutate authoritative state."""


class PlanStepSpec(BaseModel):
    step_id: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1)
    tool_name: str = Field(min_length=1, max_length=100)
    dependencies: List[str] = Field(default_factory=list)
    expected_evidence_type: Optional[str] = None
    completion_criteria: Dict[str, Any] = Field(default_factory=dict)
    inputs: Dict[str, Any] = Field(default_factory=dict)


class PlanSpec(BaseModel):
    objective: str = Field(min_length=1)
    steps: List[PlanStepSpec] = Field(min_length=1, max_length=50)

    def validate_graph(self, known_tools: Iterable[str]) -> None:
        known = set(known_tools)
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("PLAN_INVALID: duplicate step IDs")
        id_set = set(ids)
        for step in self.steps:
            if step.tool_name not in known:
                raise ValueError(f"PLAN_INVALID: unknown tool {step.tool_name}")
            if any(dep not in id_set for dep in step.dependencies):
                raise ValueError(f"PLAN_INVALID: missing dependency for {step.step_id}")
        visiting: set[str] = set()
        visited: set[str] = set()
        graph = {step.step_id: step.dependencies for step in self.steps}

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("PLAN_CYCLE: dependency cycle detected")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: Type[BaseModel]
    execute: Callable[..., Any]
    timeout_seconds: float = 30.0
    max_attempts: int = 2
    retryable_errors: tuple[str, ...] = ()
    safety_classification: str = "read_only"
    side_effect_classification: str = "none"
    available: bool = True
    version: str = "1"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"TOOL_ALREADY_REGISTERED:{definition.name}")
        self._tools[definition.name] = definition

    def replace(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            definition = self._tools[name]
        except KeyError as exc:
            raise RuntimeError(f"TOOL_UNAVAILABLE:{name}") from exc
        if not definition.available:
            raise RuntimeError(f"TOOL_UNAVAILABLE:{name}")
        return definition

    def names(self) -> List[str]:
        return sorted(self._tools)

    async def invoke(self, name: str, raw_input: Dict[str, Any], context: Any = None) -> Any:
        definition = self.get(name)
        try:
            validated = definition.input_model.model_validate(raw_input)
        except ValidationError as exc:
            raise ValueError(f"INVALID_TOOL_INPUT:{exc}") from exc
        kwargs = {"context": context, "input": validated}
        result = definition.execute(**kwargs)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, timeout=definition.timeout_seconds)
        return result


_TRANSITIONS: Dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.CREATED: {RuntimeState.PLANNING, RuntimeState.CANCELLED},
    RuntimeState.PLANNING: {RuntimeState.READY, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.READY: {RuntimeState.EXECUTING, RuntimeState.CANCELLED},
    RuntimeState.EXECUTING: {RuntimeState.READY, RuntimeState.OBSERVING, RuntimeState.VERIFYING, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.OBSERVING: {RuntimeState.VERIFYING, RuntimeState.EXECUTING, RuntimeState.REPLANNING, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.VERIFYING: {RuntimeState.EXECUTING, RuntimeState.REPLANNING, RuntimeState.SYNTHESIZING, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.REPLANNING: {RuntimeState.READY, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.SYNTHESIZING: {RuntimeState.COMPLETED, RuntimeState.FAILED, RuntimeState.CANCELLED},
    RuntimeState.COMPLETED: set(), RuntimeState.FAILED: set(), RuntimeState.CANCELLED: set(),
}


async def transition(session: AsyncSession, investigation: InvestigationSession, to_state: RuntimeState, reason: str = "", metadata: Optional[Dict[str, Any]] = None) -> AgentTransition:
    current = RuntimeState(investigation.current_state)
    if to_state not in _TRANSITIONS[current]:
        raise ValueError(f"INVALID_STATE_TRANSITION:{current.value}->{to_state.value}")
    now = datetime.now(timezone.utc)
    record = AgentTransition(investigation_id=investigation.id, from_state=current.value, to_state=to_state.value, reason=reason, metadata_json=metadata or {})
    investigation.current_state = to_state.value
    if to_state == RuntimeState.EXECUTING and investigation.started_at is None:
        investigation.started_at = now
    if to_state in {RuntimeState.COMPLETED, RuntimeState.FAILED, RuntimeState.CANCELLED}:
        investigation.completed_at = now
    session.add(record)
    await session.flush()
    await persist_runtime_event(session, investigation.id, "state.changed", logical_identity(investigation.id, "state.changed", record.id), {"from": current.value, "to": to_state.value, "reason": reason}, record.id)
    return record


async def record_observation(session: AsyncSession, investigation_id: UUID, classification: str, success: bool, summary: str, step_id: Optional[UUID] = None, attempt_id: Optional[UUID] = None, payload: Optional[Dict[str, Any]] = None) -> AgentObservation:
    observation = AgentObservation(investigation_id=investigation_id, step_id=step_id, attempt_id=attempt_id, classification=classification, success=success, summary=summary, payload=payload or {})
    session.add(observation)
    await session.flush()
    await persist_runtime_event(session, investigation_id, "observation.created", logical_identity(investigation_id, "observation.created", observation.id), {"classification": classification, "success": success}, observation.id)
    return observation


async def persist_plan(session: AsyncSession, investigation: InvestigationSession, plan: PlanSpec, generated_by: str, reason: str = "", logical_id: Optional[str] = None) -> AgentPlan:
    if logical_id:
        existing = (await session.execute(select(AgentPlan).where(AgentPlan.logical_identity == logical_id))).scalar_one_or_none()
        if existing:
            investigation.plan_version = max(investigation.plan_version, existing.version)
            return existing
    investigation.plan_version += 1
    record = AgentPlan(investigation_id=investigation.id, version=investigation.plan_version, generated_by=generated_by, reason=reason, logical_identity=logical_id)
    session.add(record)
    for sequence, spec in enumerate(plan.steps, start=1):
        record.steps.append(AgentPlanStep(sequence=sequence, step_key=spec.step_id, objective=spec.objective, tool_name=spec.tool_name, dependencies=spec.dependencies, expected_evidence_type=spec.expected_evidence_type, completion_criteria=spec.completion_criteria, inputs=spec.inputs))
    await session.flush()
    await persist_runtime_event(session, investigation.id, "plan.created", logical_identity(investigation.id, "plan.created", record.id), {"version": record.version}, record.id)
    return record


async def replan(session: AsyncSession, investigation: InvestigationSession, plan: PlanSpec, registry: ToolRegistry, reason: str, budget: RuntimeBudget) -> AgentPlan:
    """Persist a revised plan without mutating its predecessor."""
    plan.validate_graph(registry.names())
    # Compute the logical replan identity before mutating runtime state.  A
    # replay after the first transaction committed must return the existing
    # plan (and remain idempotent) even when the investigation has already
    # advanced back to READY.
    logical_id = logical_identity(investigation.id, reason.strip().lower(), plan.model_dump())
    existing = await session.scalar(select(AgentPlan).where(
        AgentPlan.investigation_id == investigation.id,
        AgentPlan.logical_identity == logical_id,
    ))
    if existing is not None:
        investigation.plan_version = max(investigation.plan_version, existing.version)
        return existing
    if investigation.plan_version >= budget.max_plan_versions:
        raise RuntimeError(RuntimeErrorCode.REPLAN_EXHAUSTED.value)
    current = RuntimeState(investigation.current_state)
    if current != RuntimeState.REPLANNING:
        await transition(session, investigation, RuntimeState.REPLANNING, reason)
    await persist_runtime_event(session, investigation.id, "replan.started", logical_identity(investigation.id, "replan.started", logical_id), {"reason": reason})
    revised = await persist_plan(session, investigation, plan, generated_by="replanner", reason=reason, logical_id=logical_id)
    await persist_runtime_event(session, investigation.id, "plan.revised", logical_identity(investigation.id, "plan.revised", logical_id), {"version": revised.version}, revised.id)
    await transition(session, investigation, RuntimeState.READY, "replan_validated", {"plan_version": investigation.plan_version})
    return revised


@dataclass(frozen=True)
class RuntimeBudget:
    max_steps: int = 12
    max_plan_versions: int = 3
    max_attempts_per_step: int = 2
    max_tool_calls: int = 24
    timeout_seconds: float = 900.0
    max_reflections_per_step: int = 2


class ObservationDecision(str, Enum):
    CONTINUE = "CONTINUE"
    VERIFY = "VERIFY"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    FAIL = "FAIL"
    COMPLETE_STEP = "COMPLETE_STEP"


class ReflectionResult(BaseModel):
    step_satisfied: bool = False
    evidence_sufficient: bool = False
    retry_recommended: bool = False
    replan_recommended: bool = False
    contradiction_detected: bool = False
    reason_code: str = Field(min_length=1)


def decide_after_observation(*, success: bool, empty: bool = False, retryable: bool = False, attempts_remaining: bool = False, evidence_valid: bool = True) -> ObservationDecision:
    """Bounded deterministic control decision; model confidence never overrides evidence validity."""
    if not success and retryable and attempts_remaining:
        return ObservationDecision.RETRY
    if not success or empty:
        return ObservationDecision.REPLAN
    if not evidence_valid:
        return ObservationDecision.REPLAN
    return ObservationDecision.VERIFY


def reflect_on_observation(*, decision: ObservationDecision, evidence_sufficient: bool, contradiction_detected: bool = False) -> ReflectionResult:
    """Bounded, structured reflection. It can recommend replanning but cannot bless invalid evidence."""
    if decision == ObservationDecision.REPLAN or not evidence_sufficient:
        return ReflectionResult(step_satisfied=False, evidence_sufficient=evidence_sufficient, replan_recommended=True, contradiction_detected=contradiction_detected, reason_code="EVIDENCE_INSUFFICIENT")
    return ReflectionResult(step_satisfied=decision in {ObservationDecision.VERIFY, ObservationDecision.COMPLETE_STEP}, evidence_sufficient=True, contradiction_detected=contradiction_detected, reason_code="STEP_SATISFIED")


async def acquire_lease(session: AsyncSession, investigation: InvestigationSession, worker_id: str, ttl_seconds: int = 120) -> bool:
    """Atomically acquire a bounded worker lease; safe across concurrent workers."""
    now = datetime.now(timezone.utc)
    expires = now.timestamp() + ttl_seconds
    from datetime import timedelta
    stmt = update(InvestigationSession).where(
        InvestigationSession.id == investigation.id,
        (InvestigationSession.worker_id.is_(None) | (InvestigationSession.lease_expires_at < now) | (InvestigationSession.worker_id == worker_id)),
    ).values(worker_id=worker_id, lease_acquired_at=now, lease_expires_at=now + timedelta(seconds=ttl_seconds))
    result = await session.execute(stmt)
    await session.flush()
    if result.rowcount:
        investigation.worker_id, investigation.lease_acquired_at, investigation.lease_expires_at = worker_id, now, now + timedelta(seconds=ttl_seconds)
        return True
    return False


async def release_lease(session: AsyncSession, investigation_id: UUID, worker_id: str) -> None:
    """Release a lease using a stable identity that survives rollback/expiry."""
    await session.execute(
        update(InvestigationSession)
        .where(
            InvestigationSession.id == investigation_id,
            InvestigationSession.worker_id == worker_id,
        )
        .values(worker_id=None, lease_acquired_at=None, lease_expires_at=None)
    )
    await session.flush()


async def renew_lease(session: AsyncSession, investigation: InvestigationSession, worker_id: str, ttl_seconds: int = 120) -> bool:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    stmt = update(InvestigationSession).where(
        InvestigationSession.id == investigation.id,
        InvestigationSession.worker_id == worker_id,
        InvestigationSession.lease_expires_at >= now,
    ).values(lease_expires_at=now + timedelta(seconds=ttl_seconds))
    result = await session.execute(stmt)
    await session.flush()
    if result.rowcount:
        investigation.lease_expires_at = now + timedelta(seconds=ttl_seconds)
        return True
    return False


async def owns_lease(session: AsyncSession, investigation_id: UUID, worker_id: str) -> bool:
    row = (await session.execute(select(InvestigationSession.worker_id, InvestigationSession.lease_expires_at).where(InvestigationSession.id == investigation_id))).one_or_none()
    return bool(row and row[0] == worker_id and row[1] and row[1] >= datetime.now(timezone.utc))


async def claim_next_investigation(session: AsyncSession, worker_id: str, ttl_seconds: int = 120) -> Optional[InvestigationSession]:
    """Claim one eligible investigation atomically on PostgreSQL."""
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    candidate = (await session.execute(select(InvestigationSession).where(
        InvestigationSession.current_state.in_([
            RuntimeState.CREATED.value,
            RuntimeState.PLANNING.value,
            RuntimeState.READY.value,
            RuntimeState.EXECUTING.value,
            RuntimeState.OBSERVING.value,
            RuntimeState.VERIFYING.value,
            RuntimeState.REPLANNING.value,
            RuntimeState.SYNTHESIZING.value,
        ]),
        InvestigationSession.cancellation_requested.is_(False),
        ((InvestigationSession.worker_id.is_(None)) | (InvestigationSession.lease_expires_at < now)),
    ).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
    if candidate is None:
        return None
    candidate.worker_id = worker_id
    candidate.lease_acquired_at = now
    candidate.lease_expires_at = now + timedelta(seconds=ttl_seconds)
    await session.flush()
    return candidate


async def prepare_claimed_investigation_for_recovery(
    session: AsyncSession,
    investigation: InvestigationSession,
) -> None:
    """Move an interrupted, newly claimed run back to a safe replay boundary."""
    current = RuntimeState(investigation.current_state)
    await session.execute(
        update(AgentToolAttempt)
        .where(
            AgentToolAttempt.step_id.in_(
                select(AgentPlanStep.id)
                .join(AgentPlan, AgentPlanStep.plan_id == AgentPlan.id)
                .where(AgentPlan.investigation_id == investigation.id)
            ),
            AgentToolAttempt.status == "RUNNING",
        )
        .values(
            status="ORPHANED",
            error_classification="WORKER_INTERRUPTED",
            retryable=True,
            completed_at=datetime.now(timezone.utc),
        )
    )
    if current in {RuntimeState.CREATED, RuntimeState.READY, RuntimeState.SYNTHESIZING}:
        return
    if current in {RuntimeState.OBSERVING, RuntimeState.VERIFYING}:
        await transition(session, investigation, RuntimeState.REPLANNING, "worker_recovery")
    await transition(session, investigation, RuntimeState.READY, "worker_recovery")


def logical_identity(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


PENDING_RUNTIME_EVENTS = "pending_runtime_events"


@dataclass(frozen=True)
class RuntimeEventNotice:
    """Transaction-independent snapshot of a persisted runtime event.

    Publication happens *after* commit, and a commit (or the rollback taken on
    the failure path) expires every ORM instance bound to the session. Reading
    an expired attribute would trigger a lazy refresh -- synchronous IO inside
    the async publish loop -- so the scalar values are captured here, while the
    instance is still loaded, and the publisher never touches the ORM again.
    """
    investigation_id: str
    event_id: str
    event_type: str
    entity_id: Optional[str]
    payload: Dict[str, Any]

    @classmethod
    def of(cls, event: RuntimeEvent) -> "RuntimeEventNotice":
        return cls(
            investigation_id=str(event.investigation_id),
            event_id=str(event.id),
            event_type=event.event_type,
            entity_id=str(event.entity_id) if event.entity_id else None,
            payload=dict(event.payload or {}),
        )


def _queue_runtime_event_notice(session: AsyncSession, event: RuntimeEvent) -> None:
    session.info.setdefault(PENDING_RUNTIME_EVENTS, {})[str(event.id)] = RuntimeEventNotice.of(event)


@sa_event.listens_for(SyncSession, "after_soft_rollback")
def _discard_rolled_back_runtime_events(session: SyncSession, previous_transaction: Any) -> None:
    """Rolled-back events were never committed, so they must never publish.

    Clearing transaction-local pending state here is what keeps the failure
    path honest: ``fail_investigation`` rolls back a partially applied
    transaction before persisting the explicit failure, and only the events
    written after that rollback may be announced.
    """
    session.info.pop(PENDING_RUNTIME_EVENTS, None)


async def persist_runtime_event(session: AsyncSession, investigation_id: UUID, event_type: str, identity: str, payload: Optional[Dict[str, Any]] = None, entity_id: Optional[UUID] = None) -> RuntimeEvent:
    existing = (await session.execute(select(RuntimeEvent).where(RuntimeEvent.logical_identity == identity))).scalar_one_or_none()
    if existing:
        return existing
    # PostgreSQL's unique constraint is the concurrency backstop.  The
    # conflict-safe insert avoids poisoning a transaction when two workers
    # replay the same lifecycle event concurrently.
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(RuntimeEvent).values(
            investigation_id=investigation_id, event_type=event_type,
            logical_identity=identity, entity_id=entity_id, payload=payload or {},
        ).on_conflict_do_nothing(index_elements=[RuntimeEvent.logical_identity])
        await session.execute(stmt)
        event = (await session.execute(select(RuntimeEvent).where(RuntimeEvent.logical_identity == identity))).scalar_one()
        _queue_runtime_event_notice(session, event)
        return event
    event = RuntimeEvent(investigation_id=investigation_id, event_type=event_type, logical_identity=identity, entity_id=entity_id, payload=payload or {})
    session.add(event)
    await session.flush()
    _queue_runtime_event_notice(session, event)
    return event


async def materialize_runtime_event_sequences(session: AsyncSession, investigation_id: UUID) -> None:
    """Assign replay order only after events are visible to a reader.

    Insert timestamps and database sequences can both be allocated before a
    transaction commits. Assigning delivery order to committed, visible rows
    prevents a later commit from falling behind an already-issued SSE cursor.
    """
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"runtime-delivery:{investigation_id}")))
        )
    next_sequence = (
        await session.execute(
            select(func.coalesce(func.max(RuntimeEvent.delivery_sequence), 0)).where(
                RuntimeEvent.investigation_id == investigation_id
            )
        )
    ).scalar_one()
    pending = (
        await session.execute(
            select(RuntimeEvent)
            .where(
                RuntimeEvent.investigation_id == investigation_id,
                RuntimeEvent.delivery_sequence.is_(None),
            )
            .order_by(RuntimeEvent.created_at.asc(), RuntimeEvent.id.asc())
            .with_for_update()
        )
    ).scalars().all()
    for event in pending:
        next_sequence += 1
        event.delivery_sequence = next_sequence
    await session.flush()


async def publish_persisted_runtime_events(session: AsyncSession) -> None:
    """Publish only events already committed by the caller's transaction.

    RuntimeEvent remains authoritative; this helper is intentionally called
    after commit by service/API boundaries and publishes the persisted event
    identity rather than constructing a transport-only lifecycle message.
    """
    pending = session.info.pop(PENDING_RUNTIME_EVENTS, {})
    if not pending:
        return
    from app.agent.sse_manager import sse_manager
    for notice in pending.values():
        await sse_manager.emit(notice.investigation_id, notice.event_type, {
            "event_id": notice.event_id,
            "event_type": notice.event_type,
            "entity_id": notice.entity_id,
            "payload": notice.payload,
        })


async def get_or_create_logical_output(session: AsyncSession, model: Any, session_id: UUID, identity: str, **values: Any) -> Any:
    """Idempotent domain-output boundary; attempts remain append-only while output is singular."""
    existing = (await session.execute(select(model).where(model.session_id == session_id, model.logical_identity == identity))).scalar_one_or_none()
    if existing:
        return existing
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(model).values(session_id=session_id, logical_identity=identity, **values)
        stmt = stmt.on_conflict_do_nothing(index_elements=[model.session_id, model.logical_identity])
        await session.execute(stmt)
        return (await session.execute(select(model).where(model.session_id == session_id, model.logical_identity == identity))).scalar_one()
    obj = model(session_id=session_id, logical_identity=identity, **values)
    session.add(obj)
    await session.flush()
    return obj


async def resume_investigation(session: AsyncSession, investigation_id: UUID, worker_id: str, ttl_seconds: int = 120) -> InvestigationSession:
    investigation = (await session.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id).with_for_update())).scalar_one()
    if RuntimeState(investigation.current_state) in {RuntimeState.COMPLETED, RuntimeState.FAILED, RuntimeState.CANCELLED}:
        raise RuntimeError("TERMINAL_INVESTIGATION")
    if investigation.cancellation_requested:
        investigation.current_state = RuntimeState.CANCELLED.value
        investigation.failure_code = RuntimeErrorCode.CANCELLED.value
        await session.commit()
        return investigation
    if not await acquire_lease(session, investigation, worker_id, ttl_seconds):
        raise RuntimeError(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
    await prepare_claimed_investigation_for_recovery(session, investigation)
    await session.commit()
    return investigation


async def record_contradiction(session: AsyncSession, investigation_id: UUID, topic: str, evidence_a_id: UUID, evidence_b_id: UUID, conflict_type: str = "NUMERIC_CONFLICT") -> ContradictionRecord:
    a, b = sorted((str(evidence_a_id), str(evidence_b_id)))
    identity = logical_identity(investigation_id, topic[:255].strip().lower(), a, b)
    existing = (await session.execute(select(ContradictionRecord).where(ContradictionRecord.logical_identity == identity))).scalar_one_or_none()
    if existing:
        return existing
    record = ContradictionRecord(investigation_id=investigation_id, topic=topic[:255], evidence_a_id=UUID(a), evidence_b_id=UUID(b), conflict_type=conflict_type, status="UNRESOLVED", logical_identity=identity, created_at=datetime.now(timezone.utc))
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


def detect_numeric_contradictions(evidence: Iterable[Dict[str, Any]]) -> List[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Conservative detector: only flags same normalized topic with differing numeric values."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence:
        text = str(item.get("exact_quote", ""))
        numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", text)
        if not numbers:
            continue
        topic = re.sub(r"\b\d+(?:\.\d+)?%?\b", "", text.lower())
        topic = re.sub(r"\s+", " ", topic).strip()
        groups.setdefault(topic, []).append(item)
    return [(items[i], items[j]) for items in groups.values() for i in range(len(items)) for j in range(i + 1, len(items)) if re.findall(r"\b\d+(?:\.\d+)?%?\b", str(items[i].get("exact_quote", ""))) != re.findall(r"\b\d+(?:\.\d+)?%?\b", str(items[j].get("exact_quote", "")))]


def is_retryable(error: BaseException, definition: ToolDefinition) -> bool:
    message = str(error).upper()
    return any(marker.upper() in message for marker in definition.retryable_errors)


class DurablePlanExecutor:
    """Dependency-aware executor used by tests and future worker orchestration.

    Every attempt and observation is append-only. The executor stops at explicit
    budget/cancellation boundaries and never silently retries deterministic errors.
    """
    def __init__(self, db: AsyncSession, registry: ToolRegistry, budget: RuntimeBudget = RuntimeBudget(), replanner: Optional[Callable[..., Awaitable[PlanSpec]]] = None) -> None:
        self.db, self.registry, self.budget, self.replanner = db, registry, budget, replanner

    async def execute(self, investigation: InvestigationSession, plan: PlanSpec, context: Any = None) -> Dict[str, Any]:
        if RuntimeState(investigation.current_state) in {RuntimeState.COMPLETED, RuntimeState.CANCELLED, RuntimeState.FAILED}:
            return {"status": RuntimeState(investigation.current_state).value, "outputs": {}}
        plan.validate_graph(self.registry.names())
        if len(plan.steps) > self.budget.max_steps:
            raise ValueError(RuntimeErrorCode.BUDGET_EXHAUSTED.value)
        current = RuntimeState(investigation.current_state)
        if current == RuntimeState.CREATED:
            await transition(self.db, investigation, RuntimeState.PLANNING, "runtime_started")
        if RuntimeState(investigation.current_state) == RuntimeState.PLANNING:
            await transition(self.db, investigation, RuntimeState.READY, "plan_validated")
        await transition(self.db, investigation, RuntimeState.EXECUTING, "plan_ready")
        plan_record = await persist_plan(self.db, investigation, plan, generated_by="runtime", reason="execution")
        await self.db.flush()
        persisted_steps = {step.step_key: step for step in plan_record.steps}
        statuses = {step.step_id: "PENDING" for step in plan.steps}
        outputs: Dict[str, Any] = {}
        calls = 0
        started = datetime.now(timezone.utc)
        while len([v for v in statuses.values() if v in {"COMPLETED", "FAILED"}]) < len(statuses):
            worker_id = context.get("worker_id") if isinstance(context, dict) else None
            if worker_id and not await owns_lease(self.db, investigation.id, worker_id):
                raise WorkerLeaseLost(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
            if investigation.cancellation_requested:
                await transition(self.db, investigation, RuntimeState.CANCELLED, RuntimeErrorCode.CANCELLED.value)
                await self.db.commit()
                return {"status": RuntimeState.CANCELLED.value, "outputs": outputs}
            if (datetime.now(timezone.utc) - started).total_seconds() > self.budget.timeout_seconds or calls >= self.budget.max_tool_calls:
                raise RuntimeError(RuntimeErrorCode.BUDGET_EXHAUSTED.value)
            runnable = [step for step in plan.steps if statuses[step.step_id] == "PENDING" and all(statuses[d] == "COMPLETED" for d in step.dependencies)]
            if not runnable:
                if any(status == "FAILED" for status in statuses.values()):
                    raise RuntimeError(RuntimeErrorCode.DEPENDENCY_FAILED.value)
                raise ValueError(RuntimeErrorCode.PLAN_CYCLE.value)
            for spec in runnable:
                definition = self.registry.get(spec.tool_name)
                db_step = persisted_steps[spec.step_id]
                statuses[spec.step_id] = "RUNNING"
                # The persisted step row mirrors the in-memory scheduler state
                # so a resumed or inspected plan reports the same lifecycle.
                db_step.status = "RUNNING"
                decision = await self._execute_step(investigation, db_step, spec, definition, context, outputs, statuses)
                await transition(self.db, investigation, RuntimeState.OBSERVING, "tool_observed")
                reflection = reflect_on_observation(
                    decision=decision,
                    evidence_sufficient=decision in {ObservationDecision.VERIFY, ObservationDecision.COMPLETE_STEP},
                )
                if reflection.replan_recommended:
                    if self.replanner is None:
                        raise RuntimeError(RuntimeErrorCode.EVIDENCE_NOT_FOUND.value)
                    await transition(self.db, investigation, RuntimeState.REPLANNING, "observation_requires_replan")
                    revised = await self.replanner(investigation=investigation, failed_step=spec, outputs=outputs)
                    await replan(self.db, investigation, revised, self.registry, "observation_requires_replan", self.budget)
                    return {"status": "replanned", "outputs": outputs}
                await transition(self.db, investigation, RuntimeState.VERIFYING, "deterministic_checks")
                await transition(self.db, investigation, RuntimeState.EXECUTING, "step_verified")
                statuses[spec.step_id] = "COMPLETED"
                db_step.status = "COMPLETED"
                await self.db.flush()
                calls += 1
        await transition(self.db, investigation, RuntimeState.VERIFYING, "all_steps_complete")
        await transition(self.db, investigation, RuntimeState.SYNTHESIZING, "verified_outputs")
        worker_id = context.get("worker_id") if isinstance(context, dict) else None
        if worker_id and not await owns_lease(self.db, investigation.id, worker_id):
            raise WorkerLeaseLost(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
        if not (isinstance(context, dict) and context.get("defer_synthesis")):
            await transition(self.db, investigation, RuntimeState.COMPLETED, "runtime_complete")
        await self.db.commit()
        return {"status": "completed", "outputs": outputs}

    async def _execute_step(self, investigation: InvestigationSession, db_step: AgentPlanStep, spec: PlanStepSpec, definition: ToolDefinition, context: Any, outputs: Dict[str, Any], statuses: Dict[str, str]) -> ObservationDecision:
        last_error: Optional[BaseException] = None
        for attempt_no in range(1, min(definition.max_attempts, self.budget.max_attempts_per_step) + 1):
            started = datetime.now(timezone.utc)
            attempt = AgentToolAttempt(step_id=db_step.id, tool_name=definition.name, tool_version=definition.version, validated_input=spec.inputs, started_at=started, status="RUNNING", retryable=False, attempt_no=attempt_no)
            self.db.add(attempt)
            db_step.attempts = attempt_no
            await self.db.flush()
            try:
                await persist_runtime_event(self.db, investigation.id, "step.started", logical_identity(investigation.id, db_step.id, "step.started"), {"step": spec.step_id}, db_step.id)
                worker_id = context.get("worker_id") if isinstance(context, dict) else None
                if worker_id and not await owns_lease(self.db, investigation.id, worker_id):
                    attempt.status = "FAILED"
                    attempt.error_classification = "WORKER_LEASE_LOST"
                    attempt.completed_at = datetime.now(timezone.utc)
                    await self.db.flush()
                    raise WorkerLeaseLost(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
                await persist_runtime_event(self.db, investigation.id, "tool.started", logical_identity(investigation.id, db_step.id, "tool.started", attempt_no), {"tool": definition.name, "attempt": attempt_no}, attempt.id)
                result = await self.registry.invoke(definition.name, spec.inputs, context)
                # Fence the completion boundary as well as the start. A lease
                # may expire while an external tool is running; a stale worker
                # must not commit its result after another worker takes over.
                if worker_id and not await owns_lease(self.db, investigation.id, worker_id):
                    attempt.status = "FAILED"
                    attempt.error_classification = "WORKER_LEASE_LOST"
                    attempt.completed_at = datetime.now(timezone.utc)
                    attempt.retryable = True
                    await self.db.flush()
                    raise WorkerLeaseLost(RuntimeErrorCode.WORKER_LEASE_UNAVAILABLE.value)
                # Promote only explicitly structured, lineage-bearing outputs;
                # arbitrary tool text never becomes evidence or a claim.
                from app.agent.persistence import persist_tool_domain_outputs
                await persist_tool_domain_outputs(
                    self.db,
                    investigation=investigation,
                    step_id=spec.step_id,
                    result=result,
                )
                outputs[spec.step_id] = result
                attempt.status = "COMPLETED"
                attempt.completed_at = datetime.now(timezone.utc)
                attempt.duration_ms = int((attempt.completed_at - started).total_seconds() * 1000)
                await persist_runtime_event(self.db, investigation.id, "tool.completed", logical_identity(investigation.id, db_step.id, "tool.completed", attempt_no), {"tool": definition.name, "attempt": attempt_no}, attempt.id)
                await record_observation(self.db, investigation.id, "SUCCESS", True, "Tool completed", payload={"step_id": spec.step_id})
                await persist_runtime_event(self.db, investigation.id, "step.verified", logical_identity(investigation.id, db_step.id, "step.verified"), {"step": spec.step_id}, db_step.id)
                await self.db.flush()
                empty = result is None or result == {} or result == [] or (isinstance(result, dict) and isinstance(result.get("results"), list) and not result.get("results"))
                return decide_after_observation(success=True, empty=empty, evidence_valid=not bool(spec.completion_criteria.get("evidence_required") and empty))
            except SimulatedWorkerCrash:
                # Preserve the RUNNING attempt exactly as an uncertain
                # external execution; the recovery worker will classify it as
                # ORPHANED and apply the normal safe retry policy.
                raise
            except WorkerLeaseLost:
                raise
            except BaseException as exc:
                last_error = exc
                retryable = is_retryable(exc, definition)
                attempt.status = "FAILED"
                attempt.completed_at = datetime.now(timezone.utc)
                attempt.duration_ms = int((attempt.completed_at - started).total_seconds() * 1000)
                attempt.error_classification = "TOOL_TIMEOUT" if isinstance(exc, asyncio.TimeoutError) else "TOOL_EXECUTION_FAILED"
                attempt.retryable = retryable
                await persist_runtime_event(self.db, investigation.id, "tool.failed", logical_identity(investigation.id, db_step.id, "tool.failed", attempt_no), {"tool": definition.name, "attempt": attempt_no}, attempt.id)
                await record_observation(self.db, investigation.id, "TIMEOUT" if isinstance(exc, asyncio.TimeoutError) else "TOOL_EXECUTION_FAILED", False, str(exc), payload={"step_id": spec.step_id, "attempt": attempt_no, "retryable": retryable})
                if not retryable or attempt_no >= min(definition.max_attempts, self.budget.max_attempts_per_step):
                    statuses[spec.step_id] = "FAILED"
                    db_step.status = "FAILED"
                    await persist_runtime_event(
                        self.db,
                        investigation.id,
                        "step.failed",
                        logical_identity(investigation.id, db_step.id, "step.failed"),
                        {"step": spec.step_id, "error": attempt.error_classification},
                        db_step.id,
                    )
                    await self.db.flush()
                    return decide_after_observation(success=False, retryable=retryable, attempts_remaining=False)
                await asyncio.sleep(0)
        return ObservationDecision.REPLAN
