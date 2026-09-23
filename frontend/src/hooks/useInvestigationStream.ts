"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AgentStep, InvestigationSession, KeyFinding } from "@/types/api";
import { apiClient } from "@/lib/api-client";

export interface InvestigationStreamState {
  objective: string;
  connection: "connecting" | "live" | "reconnecting" | "offline" | "closed";
  status:
    | "idle"
    | "created"
    | "planning"
    | "ready"
    | "running"
    | "executing"
    | "observing"
    | "verifying"
    | "replanning"
    | "synthesizing"
    | "completed"
    | "failed"
    | "cancelled";
  activitySummary: string;
  steps: AgentStep[];
  planTasks: Array<{
    id: string;
    title: string;
    target_modality: string;
    status?: string;
  }>;
  evidenceDiscovered: Array<{
    citation_id: string;
    source_name: string;
    quote: string;
    modality: string;
  }>;
  finalResponse: InvestigationSession["final_response"] | null;
  errorMessage: string | null;
  failureCode: string | null;
  timeline: RuntimeTimelineEvent[];
}

export interface RuntimeTimelineEvent {
  id: string;
  type: string;
  timestamp?: string;
  payload?: Record<string, any>;
}

const initialState: InvestigationStreamState = {
  objective: "",
  connection: "closed",
  status: "idle",
  activitySummary: "",
  steps: [],
  planTasks: [],
  evidenceDiscovered: [],
  finalResponse: null,
  errorMessage: null,
  failureCode: null,
  timeline: [],
};

type StreamLike = {
  addEventListener: (
    type: string,
    listener: (event: MessageEvent) => void,
  ) => void;
  close: () => void;
  onerror?: () => void;
  onopen?: () => void;
};

function authenticatedEventStream(
  url: string,
  investigationId: string,
): StreamLike {
  const eventTarget = new EventTarget();
  const target = eventTarget as unknown as StreamLike;
  const controller = new AbortController();
  let closed = false;
  let cursor = "";
  target.close = () => {
    closed = true;
    controller.abort();
  };
  void (async () => {
    let delay = 500;
    while (!closed) {
      try {
        if (!apiClient.getAccessToken() && !(await apiClient.refresh())) {
          target.close();
          window.location.assign("/?session=expired");
          return;
        }
        const response = await fetch(url, {
          credentials: "include",
          signal: controller.signal,
          headers: {
            Authorization: `Bearer ${apiClient.getAccessToken()}`,
            Accept: "text/event-stream",
            ...(cursor ? { "Last-Event-ID": cursor } : {}),
          },
        });
        if (response.status === 401) {
          if (await apiClient.refresh()) continue;
          target.close();
          window.location.assign("/?session=expired");
          return;
        }
        if (!response.ok || !response.body)
          throw new Error(`SSE HTTP ${response.status}`);
        target.onopen?.();
        delay = 500;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!closed) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            let eventType = "message",
              data = "",
              id = "";
            for (const line of frame.split("\n")) {
              if (line.startsWith("event:")) eventType = line.slice(6).trim();
              else if (line.startsWith("data:")) data += line.slice(5).trim();
              else if (line.startsWith("id:")) id = line.slice(3).trim();
            }
            if (id) cursor = id;
            if (data)
              eventTarget.dispatchEvent(
                new MessageEvent(eventType, { data, lastEventId: id }),
              );
          }
        }
      } catch (error) {
        if (!closed) target.onerror?.();
      }
      if (!closed) {
        target.onerror?.();
        await new Promise((resolve) => window.setTimeout(resolve, delay));
        delay = Math.min(delay * 2, 5000);
      }
    }
  })();
  return target;
}

function mergeSteps(current: AgentStep[], incoming: AgentStep[]): AgentStep[] {
  const byId = new Map(current.map((step) => [step.id, step]));
  incoming.forEach((step) => byId.set(step.id, step));
  return Array.from(byId.values()).sort(
    (a, b) => a.step_number - b.step_number,
  );
}

function eventData(event: MessageEvent): Record<string, any> {
  const envelope = JSON.parse(event.data);
  return {
    ...envelope,
    ...(envelope.payload && typeof envelope.payload === "object"
      ? envelope.payload
      : {}),
  };
}

/**
 * Reports are generated against the canonical backend `KeyFinding` contract
 * (`title`/`detail`/`claim_id`). Reports persisted before that contract was
 * enforced can carry the body under `statement` or `summary`; map those onto
 * `detail` so historical investigations still render a finding body.
 */
function normalizeKeyFinding(value: unknown): KeyFinding {
  const finding = (value ?? {}) as Record<string, unknown>;
  const body = [finding.detail, finding.statement, finding.summary].find(
    (candidate): candidate is string =>
      typeof candidate === "string" && candidate.trim().length > 0,
  );
  return {
    title: typeof finding.title === "string" ? finding.title : "",
    detail: body ?? "",
    claim_id: typeof finding.claim_id === "string" ? finding.claim_id : null,
  };
}

export function normalizeFinalResponse(
  value: InvestigationSession["final_response"] | null | undefined,
): InvestigationStreamState["finalResponse"] {
  if (!value || typeof value !== "object") return null;
  const report = value as InvestigationSession["final_response"];
  return {
    executive_summary:
      typeof report?.executive_summary === "string"
        ? report.executive_summary
        : "The investigation completed without a narrative summary.",
    key_findings: Array.isArray(report?.key_findings)
      ? report.key_findings.map(normalizeKeyFinding)
      : [],
    claims: Array.isArray(report?.claims)
      ? report.claims.map((claim) => ({
          ...claim,
          citations: Array.isArray(claim.citations) ? claim.citations : [],
          calculation_ids: Array.isArray(claim.calculation_ids)
            ? claim.calculation_ids
            : [],
          supporting_claims: Array.isArray(claim.supporting_claims)
            ? claim.supporting_claims
            : [],
          verification_errors: Array.isArray(claim.verification_errors)
            ? claim.verification_errors
            : [],
        }))
      : [],
    inferences: Array.isArray(report?.inferences) ? report.inferences : [],
    recommendations: Array.isArray(report?.recommendations)
      ? report.recommendations.map((item) => ({
          ...item,
          supported_by_claims: Array.isArray(item.supported_by_claims)
            ? item.supported_by_claims
            : [],
          supporting_inference_ids: Array.isArray(
            item.supporting_inference_ids,
          )
            ? item.supporting_inference_ids
            : [],
        }))
      : [],
    rejected_proposals: Array.isArray(report?.rejected_proposals)
      ? report.rejected_proposals
      : [],
    missing_data_warnings: Array.isArray(report?.missing_data_warnings)
      ? report.missing_data_warnings
      : [],
    contradictions: Array.isArray(report?.contradictions)
      ? report.contradictions
      : [],
  };
}

export function normalizeStreamError(
  value: unknown,
  fallback = "Investigation failed.",
): string {
  if (typeof value === "string" && value.trim()) return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.message === "string" && record.message.trim())
      return record.message;
    if (
      typeof record.error_message === "string" &&
      record.error_message.trim()
    )
      return record.error_message;
  }
  return fallback;
}

export function useInvestigationStream(investigationId: string | null) {
  const [state, setState] = useState<InvestigationStreamState>(initialState);
  const eventSourceRef = useRef<StreamLike | null>(null);

  const reset = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setState(initialState);
  }, []);

  const cancel = useCallback(async () => {
    if (!investigationId) return;
    try {
      await apiClient.post(`/investigations/${investigationId}/cancel`);
      setState((prev) => ({
        ...prev,
        status: "cancelled",
        activitySummary: "Investigation cancelled.",
      }));
    } catch (e: any) {
      setState((prev) => ({
        ...prev,
        errorMessage:
          e instanceof Error ? e.message : "Cancellation failed. Try again.",
      }));
    }
  }, [investigationId]);

  useEffect(() => {
    if (!investigationId) {
      reset();
      return;
    }

    let isMounted = true;
    setState({ ...initialState, status: "created", connection: "connecting" });
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
    const streamUrl = `${apiBase}/investigations/${investigationId}/stream`;

    // Keep the fallback poller bounded when a read takes longer than its interval.
    let syncPending = false;
    let lastSyncError: string | null = null;
    // 1. Immediate fetch & hydration from REST API
    const fetchSession = async () => {
      if (syncPending || !isMounted) return false;
      syncPending = true;
      try {
        const session = await apiClient.get<InvestigationSession>(
          `/investigations/${investigationId}`,
        );
        if (!isMounted || !session) return;
        const resolvedSyncError = lastSyncError;
        lastSyncError = null;
        if (["completed", "failed", "cancelled"].includes(session.status)) {
          setState((prev) => ({
            ...prev,
            status: session.status as any,
            objective: session.objective,
            activitySummary:
              session.status === "completed"
                ? "Investigation completed. Report synthesized."
                : session.status === "failed"
                  ? session.failure_message ||
                    session.error_message ||
                    "Investigation failed."
                  : "Investigation cancelled.",
            finalResponse:
              normalizeFinalResponse(session.final_response) ||
              prev.finalResponse,
            steps:
              session.steps && session.steps.length > 0
                ? mergeSteps(prev.steps, session.steps)
                : prev.steps,
            errorMessage:
              session.failure_message ||
              session.error_message ||
              (prev.errorMessage === resolvedSyncError
                ? null
                : prev.errorMessage),
            failureCode: session.failure_code || prev.failureCode,
          }));
          return true;
        } else {
          setState((prev) => ({
            ...prev,
            status: (session.current_state || session.status) as any,
            objective: session.objective,
            errorMessage:
              prev.errorMessage === resolvedSyncError
                ? null
                : prev.errorMessage,
            steps: session.steps
              ? mergeSteps(prev.steps, session.steps)
              : prev.steps,
          }));
        }
      } catch (err) {
        lastSyncError =
          err instanceof Error
            ? err.message
            : "Investigation could not be synchronized.";
        if (isMounted)
          setState((prev) => ({
            ...prev,
            errorMessage: lastSyncError,
          }));
      } finally {
        syncPending = false;
      }
      return false;
    };

    fetchSession();

    // 2. Open SSE stream
    const es = authenticatedEventStream(streamUrl, investigationId);
    eventSourceRef.current = es;

    setState((prev) => ({
      ...prev,
      activitySummary:
        prev.activitySummary || "Connecting to persisted runtime history.",
    }));

    const addTimelineEvent = (eventType: string, raw: Record<string, any>) => {
      const aliases: Record<string, string> = {
        investigation_started: "investigation.started",
        plan_created: "plan.created",
        status_update: "state.changed",
        task_started: "step.started",
        tool_started: "tool.started",
        tool_completed: "tool.completed",
        evidence_found: "observation.created",
        final_report: "synthesis.completed",
        cancelled: "investigation.cancelled",
        failed: "investigation.failed",
      };
      const canonicalType = aliases[eventType] || eventType;
      const payload =
        raw.payload && typeof raw.payload === "object" ? raw.payload : raw;
      const event: RuntimeTimelineEvent = {
        id: String(
          raw.event_id ||
            raw.id ||
            raw.logical_identity ||
            `${canonicalType}:${raw.step_id || raw.task_id || raw.tool || raw.citation_id || raw.created_at || "singleton"}`,
        ),
        type: String(raw.event_type || canonicalType),
        timestamp: raw.created_at || raw.timestamp,
        payload,
      };
      setState((prev) => {
        const nextState = payload.to || payload.status;
        const normalizedState =
          typeof nextState === "string" ? nextState.toLowerCase() : null;
        const status =
          normalizedState === "executing"
            ? "running"
            : normalizedState === "created"
              ? "created"
              : normalizedState;
        return prev.timeline.some((item) => item.id === event.id)
          ? prev
          : {
              ...prev,
              timeline: [...prev.timeline, event],
              ...(status &&
              !["completed", "failed", "cancelled"].includes(prev.status)
                ? { status: status as InvestigationStreamState["status"] }
                : {}),
            };
      });
    };

    const runtimeEventTypes = [
      "investigation.created",
      "investigation.started",
      "state.changed",
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
      "investigation.failed",
      "investigation.cancelled",
    ];
    runtimeEventTypes.forEach((eventType) =>
      es.addEventListener(eventType, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          addTimelineEvent(eventType, data);
          const payload =
            data.payload && typeof data.payload === "object"
              ? data.payload
              : data;
          if (eventType === "investigation.failed") {
            setState((prev) => ({
              ...prev,
              status: "failed",
              failureCode:
                typeof payload.code === "string"
                  ? payload.code
                  : prev.failureCode,
              errorMessage:
                prev.errorMessage || "The investigation could not be completed.",
            }));
          } else if (eventType === "investigation.cancelled") {
            setState((prev) => ({
              ...prev,
              status: "cancelled",
              activitySummary: "Investigation cancelled.",
            }));
          } else if (eventType === "investigation.completed") {
            void fetchSession();
          }
        } catch {
          /* ignore malformed transport frames */
        }
      }),
    );

    // 3. Fallback active poller while investigation is active
    const pollTimer = setInterval(async () => {
      if (!isMounted) return;
      const isDone = await fetchSession();
      if (isDone) {
        clearInterval(pollTimer);
        // A REST terminal snapshot can precede later SSE replay batches.
        // Retain the stream for this view's lifetime; cleanup closes it on navigation.
      }
    }, 1000);

    es.addEventListener("investigation_started", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("investigation.started", data);
      setState((prev) => ({
        ...prev,
        status: ["completed", "failed", "cancelled"].includes(prev.status)
          ? prev.status
          : "planning",
        activitySummary: `Investigation started: "${data.objective?.slice(0, 80)}..."`,
      }));
    });

    es.addEventListener("plan_created", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("plan.created", data);
      setState((prev) => ({
        ...prev,
        status: ["completed", "failed", "cancelled"].includes(prev.status)
          ? prev.status
          : "running",
        activitySummary: "Plan formulated. Executing investigation tasks...",
        planTasks: data.tasks || [],
      }));
    });

    es.addEventListener("status_update", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("state.changed", data);
      setState((prev) => ({
        ...prev,
        status: ["completed", "failed", "cancelled"].includes(prev.status)
          ? prev.status
          : data.status || prev.status,
        activitySummary: data.summary || prev.activitySummary,
      }));
    });

    es.addEventListener("task_started", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("step.started", data);
      setState((prev) => ({
        ...prev,
        status: ["completed", "failed", "cancelled"].includes(prev.status)
          ? prev.status
          : "running",
        activitySummary: `Starting task: ${data.title}...`,
        planTasks: prev.planTasks.map((t) =>
          t.id === data.task_id ? { ...t, status: "in_progress" } : t,
        ),
      }));
    });

    es.addEventListener("tool_started", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("tool.started", data);
      setState((prev) => ({
        ...prev,
        activitySummary: data.summary || `Running ${data.tool}...`,
      }));
    });

    es.addEventListener("tool_completed", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("tool.completed", data);
      setState((prev) => {
        const newStep: AgentStep = {
          id: data.step_id,
          step_number: data.step_number,
          step_type: data.step_type || "tool_call",
          user_activity_summary:
            data.user_activity_summary || `Executed ${data.tool}`,
          tool_name: data.tool,
          duration_ms: data.duration_ms || 0,
          created_at: data.created_at,
        };
        return {
          ...prev,
          steps: mergeSteps(prev.steps, [newStep]),
        };
      });
    });

    es.addEventListener("evidence_found", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("observation.created", data);
      setState((prev) => ({
        ...prev,
        evidenceDiscovered: prev.evidenceDiscovered.some(
          (item) => item.citation_id === data.citation_id,
        )
          ? prev.evidenceDiscovered
          : [
              ...prev.evidenceDiscovered,
              {
                citation_id: data.citation_id,
                source_name: data.source_name,
                quote: data.quote,
                modality: data.modality,
              },
            ],
      }));
    });

    es.addEventListener("final_report", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("synthesis.completed", data);
      if (
        typeof data.executive_summary !== "string" ||
        !Array.isArray(data.claims) ||
        !Array.isArray(data.recommendations)
      ) {
        void fetchSession();
        return;
      }
      setState((prev) => ({
        ...prev,
        status: "completed",
        activitySummary: "Investigation completed. Report synthesized.",
        finalResponse: normalizeFinalResponse(
          data as InvestigationSession["final_response"],
        ),
      }));
      clearInterval(pollTimer);
    });

    es.addEventListener("done", () => {
      // Transport completion is not evidence of a completed investigation.
      void fetchSession().then((done) => {
        if (done) {
          clearInterval(pollTimer);
        }
      });
    });

    es.addEventListener("cancelled", () => {
      addTimelineEvent("investigation.cancelled", {});
      setState((prev) => ({
        ...prev,
        status: "cancelled",
        activitySummary: "Investigation cancelled.",
      }));
      clearInterval(pollTimer);
    });

    es.addEventListener("failed", (e: MessageEvent) => {
      const data = eventData(e);
      addTimelineEvent("investigation.failed", data);
      setState((prev) => ({
        ...prev,
        status: "failed",
        failureCode:
          typeof (data.code || data.failure_code) === "string"
            ? data.code || data.failure_code
            : prev.failureCode,
        errorMessage: normalizeStreamError(
          data.error ?? data.error_message,
        ),
      }));
      clearInterval(pollTimer);
    });

    es.onerror = () => {
      if (isMounted)
        setState((prev) => ({
          ...prev,
          connection:
            typeof navigator !== "undefined" && !navigator.onLine
              ? "offline"
              : "reconnecting",
        }));
    };
    es.onopen = () => {
      if (isMounted) setState((prev) => ({ ...prev, connection: "live" }));
    };

    return () => {
      isMounted = false;
      clearInterval(pollTimer);
      es.close();
    };
  }, [investigationId, reset]);

  return { state, cancel, reset };
}
