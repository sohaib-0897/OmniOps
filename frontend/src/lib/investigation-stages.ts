import type {
  InvestigationStreamState,
  RuntimeTimelineEvent,
} from "@/hooks/useInvestigationStream";

export const INVESTIGATION_STAGES = [
  {
    id: "understand",
    label: "Understanding your request",
    detail: "Planning an evidence-grounded investigation.",
  },
  {
    id: "investigate",
    label: "Finding and reviewing evidence",
    detail: "Searching and reviewing your workspace sources.",
  },
  {
    id: "verify",
    label: "Verifying findings",
    detail: "Checking supported findings against recorded evidence.",
  },
  {
    id: "prepare",
    label: "Preparing your answer",
    detail: "Organizing verified findings into the final analysis.",
  },
  {
    id: "complete",
    label: "Analysis complete",
    detail: "The evidence-grounded report is ready.",
  },
] as const;

export type InvestigationStage = (typeof INVESTIGATION_STAGES)[number];

export interface InvestigationStageSnapshot {
  index: number;
  current: InvestigationStage;
  previous: InvestigationStage | null;
  next: InvestigationStage | null;
  detail: string;
  terminal: "completed" | "failed" | "cancelled" | null;
}

const executionStates = new Set([
  "ready",
  "running",
  "executing",
  "observing",
  "replanning",
]);

function eventStage(event: RuntimeTimelineEvent): number | null {
  const type = event.type.toLowerCase();
  const payload = event.payload || {};
  // A failure rolls back uncommitted progress events, so the failure event
  // carries the runtime state it actually stopped in.
  const target = String(
    payload.to || payload.status || payload.failed_state || "",
  ).toLowerCase();
  const reason = String(payload.reason || "").toLowerCase();

  if (
    type === "synthesis.started" ||
    type === "synthesis.completed" ||
    target === "synthesizing"
  )
    return 3;
  if (
    target === "verifying" &&
    (reason === "all_steps_complete" || reason === "verified_outputs")
  )
    return 2;
  if (
    executionStates.has(target) ||
    [
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
    ].includes(type)
  )
    return 1;
  if (
    target === "planning" ||
    type === "investigation.created" ||
    type === "investigation.started"
  )
    return 0;
  return null;
}

function stageFromTimeline(timeline: RuntimeTimelineEvent[]): number | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const resolved = eventStage(timeline[index]);
    if (resolved != null) return resolved;
  }
  return null;
}

function activeStageIndex(state: InvestigationStreamState): number {
  const timelineStage = stageFromTimeline(state.timeline);
  if (state.status === "synthesizing") return 3;
  if (state.status === "verifying") {
    const latestTransition = [...state.timeline]
      .reverse()
      .find(
        (event) =>
          event.type === "state.changed" &&
          String(event.payload?.to || "").toLowerCase() === "verifying",
      );
    const reason = String(latestTransition?.payload?.reason || "").toLowerCase();
    if (latestTransition && reason && !["all_steps_complete", "verified_outputs"].includes(reason)) return 1;
    return 2;
  }
  if (executionStates.has(state.status)) return 1;
  if (["created", "planning", "idle"].includes(state.status)) return 0;
  return timelineStage ?? 0;
}

function liveDetail(
  stageIndex: number,
  timeline: RuntimeTimelineEvent[],
): string {
  const latest = timeline[timeline.length - 1];
  if (stageIndex === 1 && latest) {
    if (latest.type === "observation.created")
      return "Reviewing the source material returned by the investigation.";
    if (["replan.started", "plan.revised"].includes(latest.type))
      return "Refining the investigation plan from recorded results.";
    if (latest.type.startsWith("tool."))
      return "Searching and analyzing your workspace sources.";
  }
  return INVESTIGATION_STAGES[stageIndex].detail;
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
  const index = terminal === "completed" ? 4 : activeStageIndex(state);
  return {
    index,
    current: INVESTIGATION_STAGES[index],
    previous: index > 0 ? INVESTIGATION_STAGES[index - 1] : null,
    next:
      terminal || index >= INVESTIGATION_STAGES.length - 1
        ? null
        : INVESTIGATION_STAGES[index + 1],
    detail: liveDetail(index, state.timeline),
    terminal,
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
