/**
 * Plain-language copy for each persisted failure code. The technical code is
 * always shown alongside, never replaced.
 */
export type FailureAction = "edit" | "sources" | "retry" | "trace";

export interface FailureCopy {
  title: string;
  body: string;
  actions: FailureAction[];
}

const COPY: Record<string, FailureCopy> = {
  EVIDENCE_NOT_FOUND: {
    title: "No matching passages were found",
    body: "The search ran, but none of this workspace's indexed passages matched the question. Nothing was written, so nothing is uncited. Try rephrasing the question or add a source that covers it.",
    actions: ["edit", "sources", "trace"],
  },
  EVIDENCE_INSUFFICIENT: {
    title: "The evidence was too thin to answer",
    body: "Passages were retrieved, but not enough to support a brief. Narrow the question or add a source that covers it.",
    actions: ["edit", "sources", "trace"],
  },
  EVIDENCE_INVALID: {
    title: "No claim survived citation checks",
    body: "A brief was drafted, but none of its claims had a citation that resolved to a matching passage, so it was discarded rather than shown uncited.",
    actions: ["retry", "edit", "trace"],
  },
  PROVIDER_UNAVAILABLE: {
    title: "The analysis model could not be reached",
    body: "The model provider did not respond. Your sources and question are saved; try again when the provider is available.",
    actions: ["retry", "trace"],
  },
  PROVIDER_MODEL_UNAVAILABLE: {
    title: "The configured model is not available",
    body: "The model provider is reachable but the configured model is not installed or enabled. An administrator needs to fix the model configuration.",
    actions: ["trace"],
  },
  PROVIDER_TIMEOUT: {
    title: "The analysis model took too long",
    body: "The model did not answer within the time limit. Try again, or ask a narrower question.",
    actions: ["retry", "edit", "trace"],
  },
  PROVIDER_CONTEXT_EXCEEDED: {
    title: "Too much evidence for the model's context",
    body: "The retrieved passages did not fit the model's context window. Ask a narrower question so fewer passages are needed.",
    actions: ["edit", "trace"],
  },
  PROVIDER_RESPONSE_INVALID: {
    title: "The model returned an unusable answer",
    body: "The model's response did not match the required structure, so it was not shown. Trying again often succeeds.",
    actions: ["retry", "trace"],
  },
  CANCELLED: {
    title: "You stopped this investigation",
    body: "Nothing after the last saved step was kept.",
    actions: ["retry", "edit"],
  },
  INVESTIGATION_FAILED: {
    title: "The investigation stopped unexpectedly",
    body: "The runtime could not complete this run. The trace records how far it got.",
    actions: ["retry", "trace"],
  },
};

export function failureCopy(code: string | null | undefined): FailureCopy {
  if (code && COPY[code]) return COPY[code];
  return {
    title: "The investigation could not finish",
    body: "The runtime stopped before a brief was saved. The trace records how far it got.",
    actions: ["retry", "trace"],
  };
}

/** Short one-line label for history rows. */
export function failureShort(code: string | null | undefined): string {
  if (code === "EVIDENCE_NOT_FOUND") return "Stopped: no matching passages found";
  if (code === "CANCELLED") return "Stopped by you";
  return "Stopped";
}
