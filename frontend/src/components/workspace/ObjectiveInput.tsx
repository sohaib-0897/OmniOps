"use client";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUpRight, Loader2, Square } from "lucide-react";

interface Props {
  onStartInvestigation: (objective: string, maxSteps: number) => void;
  onCancel?: () => void;
  isRunning: boolean;
  submitting?: boolean;
  currentPhase?: string;
  activitySummary?: string | null;
}
export function ObjectiveInput({
  onStartInvestigation,
  onCancel,
  isRunning,
  submitting = false,
}: Props) {
  const [objective, setObjective] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const disabled = isRunning || submitting;
  const run = () => {
    if (objective.trim() && !disabled)
      onStartInvestigation(objective.trim(), 12);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    run();
  };
  const shortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      run();
    }
  };
  return (
    <section className="surface composer overflow-hidden">
      <div className="px-5 pt-5">
        <p className="eyebrow">Investigation objective</p>
        <h1 className="page-title mt-2">
          What do you need to understand?
        </h1>
        <p className="meta-copy mt-2">
          Add sources, ask a question, then inspect the findings and their evidence.
        </p>
      </div>
      <form onSubmit={submit} className="p-4 sm:p-5">
        <label htmlFor="objective-input" className="sr-only">
          Investigation objective
        </label>
        <textarea
          ref={input}
          id="objective-input"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          onKeyDown={shortcut}
          disabled={disabled}
          rows={5}
          placeholder="e.g. Compare quarterly margins, explain the variance, and cite the supporting sources."
          className="field min-h-36 resize-y leading-7 disabled:opacity-60"
        />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-[11px] text-zinc-400">
            <kbd className="rounded border border-zinc-700 px-1.5 py-0.5 font-sans">
              Ctrl / ⌘
            </kbd>{" "}
            + <kbd className="font-sans">Enter</kbd> to run
          </span>
          <div className="flex gap-2">
            {isRunning && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="btn-destructive"
              >
                <Square className="h-3.5 w-3.5" />
                Cancel
              </button>
            )}
            <button
              type="submit"
              disabled={disabled || !objective.trim()}
              className="btn-primary"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUpRight className="h-4 w-4" />
              )}
              {submitting
                ? "Starting"
                : isRunning
                  ? "Investigation running"
                  : "Run investigation"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
