"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { AgentStep, InvestigationSession } from "@/types/api";
import { apiClient } from "@/lib/api-client";

export interface InvestigationStreamState {
  status: "idle" | "planning" | "running" | "verifying" | "synthesizing" | "completed" | "failed" | "cancelled";
  activitySummary: string;
  steps: AgentStep[];
  planTasks: Array<{ id: string; title: string; target_modality: string; status?: string }>;
  evidenceDiscovered: Array<{ citation_id: string; source_name: string; quote: string; modality: string }>;
  finalResponse: InvestigationSession["final_response"] | null;
  errorMessage: string | null;
}

const initialState: InvestigationStreamState = {
  status: "idle",
  activitySummary: "",
  steps: [],
  planTasks: [],
  evidenceDiscovered: [],
  finalResponse: null,
  errorMessage: null,
};

function mergeSteps(current: AgentStep[], incoming: AgentStep[]): AgentStep[] {
  const byId = new Map(current.map((step) => [step.id, step]));
  incoming.forEach((step) => byId.set(step.id, step));
  return Array.from(byId.values()).sort((a, b) => a.step_number - b.step_number);
}

export function useInvestigationStream(investigationId: string | null) {
  const [state, setState] = useState<InvestigationStreamState>(initialState);
  const eventSourceRef = useRef<EventSource | null>(null);

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
      setState((prev) => ({ ...prev, status: "cancelled", activitySummary: "Investigation cancelled." }));
    } catch (e: any) {
      console.error("Failed to cancel investigation:", e);
    }
  }, [investigationId]);

  useEffect(() => {
    if (!investigationId) {
      reset();
      return;
    }

    let isMounted = true;
    const token = typeof window !== "undefined" ? localStorage.getItem("omniops_token") : "";
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
    const streamUrl = `${apiBase}/investigations/${investigationId}/stream?token=${encodeURIComponent(token || "")}`;

    // 1. Immediate fetch & hydration from REST API
    const fetchSession = async () => {
      try {
        const session = await apiClient.get<InvestigationSession>(`/investigations/${investigationId}`);
        if (!isMounted || !session) return;
        if (["completed", "failed", "cancelled"].includes(session.status)) {
          setState((prev) => ({
            ...prev,
            status: session.status as any,
            activitySummary:
              session.status === "completed"
                ? "Investigation completed. Report synthesized."
                : session.status === "failed"
                ? session.error_message || "Investigation failed."
                : "Investigation cancelled.",
            finalResponse: session.final_response || prev.finalResponse,
            steps: session.steps && session.steps.length > 0 ? mergeSteps(prev.steps, session.steps) : prev.steps,
            errorMessage: session.error_message || prev.errorMessage,
          }));
          return true;
        } else if (session.steps && session.steps.length > 0) {
          setState((prev) => ({
            ...prev,
            status: session.status as any,
            steps: session.steps ? mergeSteps(prev.steps, session.steps) : prev.steps,
          }));
        }
      } catch (err) {
        console.warn("Investigation sync notice:", err);
      }
      return false;
    };

    fetchSession();

    // 2. Open SSE stream
    const es = new EventSource(streamUrl);
    eventSourceRef.current = es;

    setState((prev) => ({
      ...prev,
      status: prev.status === "completed" ? "completed" : "planning",
      activitySummary: prev.activitySummary || "Connecting to agent...",
    }));

    // 3. Fallback active poller while investigation is active
    const pollTimer = setInterval(async () => {
      if (!isMounted) return;
      const isDone = await fetchSession();
      if (isDone) {
        clearInterval(pollTimer);
        es.close();
      }
    }, 1000);

    es.addEventListener("investigation_started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: "planning",
        activitySummary: `Investigation started: "${data.objective?.slice(0, 80)}..."`,
      }));
    });

    es.addEventListener("plan_created", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: "running",
        activitySummary: "Plan formulated. Executing investigation tasks...",
        planTasks: data.tasks || [],
      }));
    });

    es.addEventListener("status_update", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: data.status || prev.status,
        activitySummary: data.summary || prev.activitySummary,
      }));
    });

    es.addEventListener("task_started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: "running",
        activitySummary: `Starting task: ${data.title}...`,
        planTasks: prev.planTasks.map((t) => (t.id === data.task_id ? { ...t, status: "in_progress" } : t)),
      }));
    });

    es.addEventListener("tool_started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        activitySummary: data.summary || `Running ${data.tool}...`,
      }));
    });

    es.addEventListener("tool_completed", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => {
        const newStep: AgentStep = {
          id: data.step_id,
          step_number: data.step_number,
          step_type: data.step_type || "tool_call",
          user_activity_summary: data.user_activity_summary || `Executed ${data.tool}`,
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
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        evidenceDiscovered: [
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
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: "completed",
        activitySummary: "Investigation completed. Report synthesized.",
        finalResponse: data,
      }));
      clearInterval(pollTimer);
    });

    es.addEventListener("done", () => {
      setState((prev) => ({ ...prev, status: "completed" }));
      clearInterval(pollTimer);
      es.close();
    });

    es.addEventListener("cancelled", () => {
      setState((prev) => ({ ...prev, status: "cancelled", activitySummary: "Investigation cancelled." }));
      clearInterval(pollTimer);
      es.close();
    });

    es.addEventListener("failed", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({ ...prev, status: "failed", errorMessage: data.error || "Investigation failed." }));
      clearInterval(pollTimer);
      es.close();
    });

    es.onerror = () => {
      // Reconnection handled automatically by browser EventSource
    };

    return () => {
      isMounted = false;
      clearInterval(pollTimer);
      es.close();
    };
  }, [investigationId, reset]);

  return { state, cancel, reset };
}
