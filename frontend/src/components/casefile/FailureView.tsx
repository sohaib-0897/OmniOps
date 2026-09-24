"use client";

import { AlertCircle } from "lucide-react";
import type { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import { deriveInvestigationStage, INVESTIGATION_STAGES } from "@/lib/investigation-stages";
import { failureCopy, type FailureAction } from "@/lib/failure-copy";

const ACTION_LABEL: Record<FailureAction, string> = {
  edit: "Edit question",
  sources: "Add a source",
  retry: "Try again",
  trace: "Open trace",
};

/** Honest edges: plain language for the saved failure code, at the stage it stopped. */
export function FailureView({
  stream,
  onAction,
  canEdit,
}: {
  stream: InvestigationStreamState;
  onAction: (action: FailureAction) => void;
  canEdit: boolean;
}) {
  const snapshot = deriveInvestigationStage(stream);
  const cancelled = stream.status === "cancelled";
  const code = cancelled ? "CANCELLED" : stream.failureCode;
  const copy = failureCopy(code);
  const stage = INVESTIGATION_STAGES[Math.min(snapshot.index, INVESTIGATION_STAGES.length - 1)];
  const actions = copy.actions.filter((action) => canEdit || action === "trace");
  return (
    <section className="mt-8 rounded-pane border border-line bg-surface p-6" role="alert" aria-labelledby="failure-title">
      <div className="flex items-start gap-3">
        <AlertCircle className={`mt-1 h-5 w-5 shrink-0 ${cancelled ? "text-ink-2" : "text-critical"}`} aria-hidden="true" />
        <div className="min-w-0">
          <p className="t-meta text-ink-3">
            {cancelled ? "Stopped" : "Analysis couldn’t continue"}
            {snapshot.stageKnown && <> · stopped during {stage.label.toLowerCase()}</>}
          </p>
          <h2 id="failure-title" className="r-title mt-1 text-ink">{copy.title}</h2>
          <p className="r-body mt-3 max-w-[560px] text-ink-2">{copy.body}</p>
          {stream.errorMessage && !cancelled && stream.errorMessage !== copy.body && (
            <p className="t-meta mt-3 text-ink-3">Runtime message: {stream.errorMessage}</p>
          )}
          {code && <p className="mono mt-3 text-ink-3">{code}</p>}
          <div className="mt-5 flex flex-wrap gap-2">
            {actions.map((action, index) => (
              <button key={action} type="button" className={index === 0 ? "btn-primary" : "btn-outline"} onClick={() => onAction(action)}>
                {ACTION_LABEL[action]}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
