import type {
  InvestigationStreamState,
  RuntimeTimelineEvent,
} from "@/hooks/useInvestigationStream";

/**
 * The five stages follow the real runtime order. Planning and every tool step
 * commit together in one transaction, and synthesis plus claim verification
 * commit together in a second one, so the browser legitimately sees:
 * created → (batch: plan, search, evidence) → (completed | failed).
 */
export const INVESTIGATION_STAGES = [
  {
    id: "understand",
    label: "Understanding",
    detail: "Planning and searching",
  },
  {
    id: "search",
    label: "Searching",
    detail: "Searching your sources",
  },
  {
    id: "evidence",
    label: "Evidence",
    detail: "Reviewing retrieved passages",
  },
  {
    id: "write",
    label: "Writing",
    detail: "Writing the brief, then checking every citation",
  },
  {
    id: "verify",
    label: "Verification",
    detail: "Citations checked against their passages",
  },
] as const;

export type InvestigationStage = (typeof INVESTIGATION_STAGES)[number];
export type StageId = InvestigationStage["id"];

export interface InvestigationStageSnapshot {
  /** Index of the current (or failed) stage; 5 when completed. */
  index: number;
  current: InvestigationStage;
  previous: InvestigationStage | null;
  next: InvestigationStage | null;
  detail: string;
  terminal: "completed" | "failed" | "cancelled" | null;
  /** True once the planning/search batch has been persisted and received. */
  batchReceived: boolean;
  /** False for a stopped run whose stopping stage has not been received (e.g. no SSE replay yet). */
  stageKnown: boolean;
}

const searchStates = new Set(["ready", "running", "executing"]);
const evidenceStates = new Set(["observing", "verifying", "replanning"]);

const batchEventTypes = new Set([
  "plan.created",
  "step.started",
  "tool.started",
  "tool.completed",
  "tool.failed",
  "observation.created",
  "step.verified",
  "step.failed",
  "replan.started",
  "plan.revised",
  "contradiction.created",
  "synthesis.started",
  "synthesis.completed",
  "investigation.completed",
]);

function stateIndex(state: string, code?: string | null): number | null {
  const value = state.toLowerCase();
  if (value === "created" || value === "planning" || value === "idle") return 0;
  if (searchStates.has(value)) return 1;
  if (evidenceStates.has(value)) return 2;
  if (value === "synthesizing") return code === "EVIDENCE_INVALID" ? 4 : 3;
  return null;
}

function eventStage(event: RuntimeTimelineEvent): number | null {
  const type = event.type.toLowerCase();
  const payload = event.payload || {};
  if (type === "investigation.failed") {
    // A failure rolls back uncommitted progress, so it carries the state it
    // actually stopped in.
    const failed = typeof payload.failed_state === "string" ? payload.failed_state : "";
    return stateIndex(failed, typeof payload.code === "string" ? payload.code : null) ?? 0;
  }
  if (type === "synthesis.started" || type === "synthesis.completed") return 3;
  const target = String(payload.to || payload.status || "").toLowerCase();
  if (target) {
    const resolved = stateIndex(target);
    if (resolved != null) return resolved;
  }
  if (["tool.started", "tool.completed", "tool.failed", "step.started"].includes(type)) return 1;
  if (["observation.created", "step.verified", "step.failed", "replan.started", "plan.revised", "contradiction.created"].includes(type)) return 2;
  if (type === "plan.created" || type === "investigation.created" || type === "investigation.started") return 0;
  return null;
}

export function batchReceived(timeline: RuntimeTimelineEvent[]): boolean {
  return timeline.some((event) => {
    if (batchEventTypes.has(event.type)) return true;
    // Any persisted transition past planning belongs to the saved batch.
    if (event.type !== "state.changed") return false;
    const to = String(event.payload?.to || "").toLowerCase();
    return Boolean(to) && !["created", "planning"].includes(to);
  });
}

function stageFromTimeline(timeline: RuntimeTimelineEvent[]): number | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const resolved = eventStage(timeline[index]);
    if (resolved != null) return resolved;
  }
  return null;
}

function activeStageIndex(state: InvestigationStreamState): number {
  const fromState = stateIndex(state.status, state.failureCode);
  const fromTimeline = stageFromTimeline(state.timeline);
  if (state.status === "failed") {
    const failure = [...state.timeline].reverse().find((event) => event.type === "investigation.failed");
    return failure ? eventStage(failure) ?? 0 : fromTimeline ?? 0;
  }
  if (state.status === "cancelled") return fromTimeline ?? 0;
  // When the batch has arrived, Writing is current even if the status poll lags.
  if (batchReceived(state.timeline) && (fromState ?? 0) < 3 && fromTimeline != null && fromTimeline >= 3) return 3;
  return Math.max(fromState ?? 0, fromTimeline ?? 0);
}

/**
 * Derive the human-facing stage only from persisted runtime state/events.
 * There is intentionally no elapsed-time input and no timer-based advancement.
 */
export function deriveInvestigationStage(
  state: InvestigationStreamState,
): InvestigationStageSnapshot {
  const terminal = ["completed", "failed", "cancelled"].includes(state.status)
    ? (state.status as InvestigationStageSnapshot["terminal"])
    : null;
  const index = terminal === "completed" ? INVESTIGATION_STAGES.length : Math.min(activeStageIndex(state), INVESTIGATION_STAGES.length - 1);
  const clamped = Math.min(index, INVESTIGATION_STAGES.length - 1);
  return {
    index,
    current: INVESTIGATION_STAGES[clamped],
    previous: clamped > 0 ? INVESTIGATION_STAGES[clamped - 1] : null,
    next: terminal || clamped >= INVESTIGATION_STAGES.length - 1 ? null : INVESTIGATION_STAGES[clamped + 1],
    detail: INVESTIGATION_STAGES[clamped].detail,
    terminal,
    // Planning through synthesis commit as one transaction, so a persisted (polled)
    // state past planning also proves the batch is saved, even without SSE events.
    batchReceived: batchReceived(state.timeline) || terminal === "completed" || (!terminal && (stateIndex(state.status) ?? 0) >= 1),
    // Only the persisted failure event records where a failed run stopped; polled status cannot.
    stageKnown:
      terminal === "failed"
        ? state.timeline.some((event) => event.type === "investigation.failed")
        : terminal === "cancelled"
          ? stageFromTimeline(state.timeline) != null
          : true,
  };
}

export function runtimeDuration(timeline: RuntimeTimelineEvent[]): number | null {
  const times = timeline
    .map((event) => (event.timestamp ? Date.parse(event.timestamp) : NaN))
    .filter(Number.isFinite);
  if (times.length < 2) return null;
  const duration = Math.max(...times) - Math.min(...times);
  return duration > 0 ? duration : null;
}

/** A completed report does not prove that every possible stage was observed. */
export function observedInvestigationStages(timeline: RuntimeTimelineEvent[]): InvestigationStage[] {
  const observed = new Set(timeline.map(eventStage).filter((index): index is number => index != null));
  return INVESTIGATION_STAGES.filter((_, index) => observed.has(index));
}

const eventLabels: Record<string, string> = {
  "investigation.created": "Investigation created",
  "investigation.started": "Investigation started",
  "plan.created": "Plan created",
  "plan.revised": "Plan revised",
  "step.started": "Step started",
  "step.verified": "Step verified",
  "step.failed": "Step failed",
  "tool.started": "Tool started",
  "tool.completed": "Tool completed",
  "tool.failed": "Tool failed",
  "observation.created": "Observation saved",
  "replan.started": "Replanning",
  "contradiction.created": "Contradiction recorded",
  "synthesis.started": "Writing started",
  "synthesis.completed": "Brief written",
  "investigation.completed": "Investigation completed",
  "investigation.failed": "Investigation stopped",
  "investigation.cancelled": "Investigation cancelled",
};

const toolLabels: Record<string, string> = {
  hybrid_document_search: "Search completed",
  tabular_sql_query: "Query completed",
  python_sandbox: "Calculation completed",
  web_fetch: "Web fetch completed",
};

/** A short, safe label for a persisted event. Payload text is never echoed. */
export function describeEvent(event: RuntimeTimelineEvent): { label: string; detail: string | null } {
  const payload = event.payload || {};
  const tool = typeof payload.tool === "string" && /^[a-z0-9_.-]{1,64}$/i.test(payload.tool) ? payload.tool : null;
  if (event.type === "tool.completed" && tool) return { label: toolLabels[tool] ?? "Tool completed", detail: tool };
  if (event.type === "state.changed") {
    const to = String(payload.to || "").toLowerCase();
    if (to === "synthesizing") return { label: "Writing started", detail: null };
    if (to === "executing") return { label: "Search started", detail: null };
    if (to === "observing") return { label: "Reviewing evidence", detail: null };
    if (to === "planning") return { label: "Planning", detail: null };
    return { label: "State changed", detail: /^[a-z_]{1,32}$/.test(to) ? to : null };
  }
  if (event.type === "plan.created") {
    const steps = Array.isArray(payload.steps) ? payload.steps.length : typeof payload.step_count === "number" ? payload.step_count : null;
    return { label: "Plan created", detail: steps != null ? `${steps} ${steps === 1 ? "step" : "steps"}` : null };
  }
  return { label: eventLabels[event.type] ?? event.type, detail: tool };
}
