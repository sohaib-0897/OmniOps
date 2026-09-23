"use client";

import { AlertCircle, Check, ChevronDown, Circle, Square } from "lucide-react";
import { useEffect, useLayoutEffect, useRef } from "react";
import type { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import {
  observedInvestigationStages,
  deriveInvestigationStage,
  runtimeDuration,
} from "@/lib/investigation-stages";
import { formatDuration } from "@/lib/utils";

const useStageLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

interface Props {
  streamState: InvestigationStreamState;
  sourceCount?: number | null;
  verifiedClaimCount?: number | null;
  onCancel?: () => void;
  onRetry?: () => void;
  onViewTechnical?: () => void;
}

function FailureDetails({ code }: { code?: string | null }) {
  if (!code) return null;
  return (
    <details className="mt-4 text-xs text-zinc-400">
      <summary>Technical details</summary>
      <p className="mt-2 break-all font-mono text-zinc-300">{code}</p>
    </details>
  );
}

export function InvestigationProgress({
  streamState,
  sourceCount,
  verifiedClaimCount,
  onCancel,
  onRetry,
  onViewTechnical,
}: Props) {
  const snapshot = deriveInvestigationStage(streamState);
  const stageWindow = useRef<HTMLDivElement>(null);
  const progressSurface = useRef<HTMLElement | null>(null);
  const previousHeight = useRef<number | null>(null);
  const positions = useRef(new Map<string, number>());
  useStageLayoutEffect(() => {
    const surface = progressSurface.current;
    if (surface) {
      const height = surface.offsetHeight;
      if (snapshot.terminal === "completed" && previousHeight.current != null && !window.matchMedia("(prefers-reduced-motion: reduce)").matches && surface.animate) {
        surface.animate([{ height: `${previousHeight.current}px`, opacity: 0.7 }, { height: `${height}px`, opacity: 1 }], { duration: 320, easing: "cubic-bezier(0.22, 1, 0.36, 1)" });
      }
      previousHeight.current = height;
    }
    const rows = stageWindow.current?.querySelectorAll<HTMLElement>("[data-stage-row]");
    const nextPositions = new Map<string, number>();
    rows?.forEach((row) => {
      const id = row.dataset.stageRow!;
      const top = row.offsetTop;
      const previous = positions.current.get(id);
      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches && row.animate) {
        row.getAnimations().forEach((animation) => animation.cancel());
        row.animate([
          { transform: `translateY(${previous == null ? 10 : previous - top}px)`, opacity: previous == null ? 0 : 1 },
          { transform: "translateY(0)", opacity: 1 },
        ], { duration: 360, easing: "cubic-bezier(0.22, 1, 0.36, 1)" });
      }
      nextPositions.set(id, top);
    });
    positions.current = nextPositions;
  }, [snapshot.current.id, snapshot.terminal]);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const stopMotion = () => { if (preference.matches) progressSurface.current?.getAnimations({ subtree: true }).forEach(animation => animation.cancel()); };
    preference.addEventListener("change", stopMotion);
    return () => preference.removeEventListener("change", stopMotion);
  }, []);
  const duration = runtimeDuration(streamState.timeline);
  const counts = [
    sourceCount != null
      ? `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`
      : null,
    verifiedClaimCount != null
      ? `${verifiedClaimCount} verified ${verifiedClaimCount === 1 ? "claim" : "claims"}`
      : null,
    duration != null ? formatDuration(duration) : null,
  ].filter(Boolean);

  if (snapshot.terminal === "completed") {
    return (
      <details ref={(node) => { progressSurface.current = node; }} className="analysis-complete-row group" data-stage-id="complete">
        <summary className="completion-summary min-h-12 list-none py-2 text-sm text-zinc-200">
          <span className="stage-complete-icon" aria-hidden="true">
            <Check className="h-3.5 w-3.5" />
          </span>
          <span className="completion-label font-medium" role="status">Analysis complete</span>
          {counts.length > 0 && (
            <span className="completion-counts text-xs text-zinc-400">
              · {counts.join(" · ")}
            </span>
          )}
          <ChevronDown className="completion-chevron h-4 w-4 text-zinc-400 transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-zinc-800 pb-4 pt-3">
          <ol className="space-y-2" aria-label="Recorded investigation stages">
            {observedInvestigationStages(streamState.timeline).map((stage) => (
              <li key={stage.id} className="flex items-center gap-3 text-xs text-zinc-400">
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{stage.label}</span>
              </li>
            ))}
          </ol>
          {observedInvestigationStages(streamState.timeline).length === 0 && <p className="text-xs text-zinc-400">Stage history is not available in this view. Open technical activity to inspect recorded events.</p>}
          {onViewTechnical && (
            <button className="btn-ghost mt-3 h-8 px-0" onClick={onViewTechnical}>
              View technical activity →
            </button>
          )}
        </div>
      </details>
    );
  }

  const failed = snapshot.terminal === "failed";
  const cancelled = snapshot.terminal === "cancelled";
  const terminalMessage = failed
    ? streamState.errorMessage || "The investigation could not be completed."
    : cancelled
      ? "This investigation was cancelled. Persisted activity remains available."
      : null;

  return (
    <section
      className="investigation-progress"
      ref={(node) => { progressSurface.current = node; }}
      aria-label="Investigation progress"
      aria-busy={!snapshot.terminal}
      data-stage-id={snapshot.current.id}
      data-stage-index={snapshot.index}
    >
      <p
        className="sr-only"
        role={failed ? "alert" : "status"}
        aria-live={failed ? "assertive" : "polite"}
        aria-atomic="true"
      >
        {failed ? "Investigation failed" : `Current stage: ${snapshot.current.label}`}.{" "}
        {terminalMessage || snapshot.detail}
      </p>
      <div
        ref={stageWindow}
        className="investigation-stage-window"
        aria-hidden="true"
      >
        {snapshot.previous && (
          <div key={snapshot.previous.id} data-stage-row={snapshot.previous.id} className="investigation-stage-row stage-previous">
            <span className="stage-marker stage-marker-complete">
              <Check className="h-3.5 w-3.5" />
            </span>
            <span>{snapshot.previous.label}</span>
          </div>
        )}
        <div key={snapshot.current.id} data-stage-row={snapshot.current.id} className={`investigation-stage-row stage-current ${failed ? "stage-failed" : ""}`}>
          <span className="stage-marker stage-marker-current">
            {failed ? <AlertCircle className="h-4 w-4" /> : cancelled ? <Square className="h-3 w-3" /> : <span className="h-2 w-2 rounded-full bg-current" />}
          </span>
          <div className="min-w-0">
            <p className="text-base font-medium tracking-tight">
              {failed ? "Analysis couldn’t continue" : cancelled ? "Investigation cancelled" : snapshot.current.label}
            </p>
            <p className="mt-1 text-sm leading-6 text-zinc-400">
              {terminalMessage || snapshot.detail}
            </p>
            {failed && <p className="mt-2 text-xs text-zinc-400">Stopped while {snapshot.current.label.toLowerCase()}.</p>}
          </div>
        </div>
        {snapshot.next && (
          <div key={snapshot.next.id} data-stage-row={snapshot.next.id} className="investigation-stage-row stage-next">
            <span className="stage-marker">
              <Circle className="h-3.5 w-3.5" />
            </span>
            <span>{snapshot.next.label}</span>
          </div>
        )}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {!snapshot.terminal && onCancel && (
          <button className="btn-ghost h-9 text-zinc-400" onClick={onCancel}>
            <Square className="h-3 w-3" />
            Cancel
          </button>
        )}
        {failed && onRetry && (
          <button className="btn-secondary" onClick={onRetry}>
            Try again
          </button>
        )}
        {snapshot.terminal && onViewTechnical && (
          <button className="btn-ghost" onClick={onViewTechnical}>
            View technical activity
          </button>
        )}
      </div>
      <FailureDetails code={streamState.failureCode} />
    </section>
  );
}
