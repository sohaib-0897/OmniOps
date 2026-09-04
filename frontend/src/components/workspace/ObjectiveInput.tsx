"use client";

import React, { useState, useRef } from "react";
import { Play, Loader2, StopCircle, ArrowRight, Sliders, Check, Search } from "lucide-react";

interface Props {
  onStartInvestigation: (objective: string, maxSteps: number) => void;
  onCancel?: () => void;
  isRunning: boolean;
  currentPhase?: string;
  activitySummary?: string | null;
}

const PRESETS = [
  {
    title: "Quarterly Revenue Variance",
    prompt: "Analyze why enterprise revenue declined in Q3, calculate segment variance in DuckDB, and synthesize strategic recovery actions.",
  },
  {
    title: "Supplier Invoice Reconciliation",
    prompt: "Cross-reference supplier invoice spreadsheets with executive meeting transcripts to identify unauthorized pricing discrepancies.",
  },
  {
    title: "Segment Churn & Margin Risk",
    prompt: "Compute customer churn variance across product segments and identify primary operational margin risk factors.",
  },
];

type DepthPreset = "quick" | "standard" | "comprehensive";

export function ObjectiveInput({
  onStartInvestigation,
  onCancel,
  isRunning,
  currentPhase,
  activitySummary,
}: Props) {
  const [objective, setObjective] = useState("");
  const [depth, setDepth] = useState<DepthPreset>("standard");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const getStepCount = (d: DepthPreset): number => {
    switch (d) {
      case "quick":
        return 6;
      case "comprehensive":
        return 18;
      case "standard":
      default:
        return 12;
    }
  };

  const handleSelectPreset = (promptText: string) => {
    setObjective(promptText);
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(promptText.length, promptText.length);
      }
    }, 50);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!objective.trim() || isRunning) return;
    onStartInvestigation(objective.trim(), getStepCount(depth));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (objective.trim() && !isRunning) {
        onStartInvestigation(objective.trim(), getStepCount(depth));
      }
    }
  };

  const isInputValid = objective.trim().length > 0;

  return (
    <div className="border border-zinc-800 bg-zinc-950 rounded-2xl p-4 sm:p-5 shadow-xl space-y-4 font-sans">
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label
              htmlFor="objective-input"
              className="text-xs font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2"
            >
              <Search className="w-3.5 h-3.5 text-zinc-400" />
              <span>Investigation Objective</span>
            </label>
            <span className="text-[10px] text-zinc-500 font-mono hidden sm:inline">
              Ctrl+Enter to execute
            </span>
          </div>

          <textarea
            ref={textareaRef}
            id="objective-input"
            rows={2}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isRunning}
            placeholder="E.g., Analyze why enterprise revenue declined in Q3, compute segment margin variance in DuckDB, and synthesize strategic actions..."
            className="w-full text-xs sm:text-sm bg-zinc-900 focus:bg-zinc-900/90 border border-zinc-800 focus:border-zinc-600 rounded-xl p-3 text-zinc-100 placeholder:text-zinc-500 resize-none outline-none leading-relaxed transition-all"
          />
        </div>

        {/* Query Templates */}
        {!isRunning && (
          <div className="flex items-center gap-2 flex-wrap pt-0.5">
            <span className="text-[11px] text-zinc-400 font-semibold">Templates:</span>
            {PRESETS.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSelectPreset(preset.prompt)}
                title={`Populate: "${preset.prompt}"`}
                className="group flex items-center gap-1.5 text-[11px] text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 px-2.5 py-1 rounded-lg text-left transition-all cursor-pointer"
              >
                <ArrowRight className="w-3 h-3 text-zinc-400 group-hover:translate-x-0.5 transition-transform shrink-0" />
                <span className="font-medium truncate max-w-xs">{preset.title}</span>
              </button>
            ))}
          </div>
        )}

        {/* Execution Depth & Action CTA */}
        <div className="flex items-center justify-between flex-wrap gap-3 pt-2.5 border-t border-zinc-850">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1">
              <Sliders className="w-3.5 h-3.5 text-zinc-500" />
              <span>Depth:</span>
            </span>
            <div className="flex items-center gap-1 bg-zinc-900 p-0.5 rounded-lg border border-zinc-800">
              <button
                type="button"
                disabled={isRunning}
                onClick={() => setDepth("quick")}
                className={`px-2.5 py-0.5 rounded text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                  depth === "quick"
                    ? "bg-white text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
                title="6 Steps"
              >
                {depth === "quick" && <Check className="w-3 h-3" />}
                <span>Quick</span>
              </button>
              <button
                type="button"
                disabled={isRunning}
                onClick={() => setDepth("standard")}
                className={`px-2.5 py-0.5 rounded text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                  depth === "standard"
                    ? "bg-white text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
                title="12 Steps"
              >
                {depth === "standard" && <Check className="w-3 h-3" />}
                <span>Standard</span>
              </button>
              <button
                type="button"
                disabled={isRunning}
                onClick={() => setDepth("comprehensive")}
                className={`px-2.5 py-0.5 rounded text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                  depth === "comprehensive"
                    ? "bg-white text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
                title="18 Steps"
              >
                {depth === "comprehensive" && <Check className="w-3 h-3" />}
                <span>Comprehensive</span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isRunning && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 text-zinc-300 hover:text-white text-xs font-semibold border border-zinc-800 hover:bg-zinc-800 transition-colors cursor-pointer"
              >
                <StopCircle className="w-3.5 h-3.5 text-zinc-400" />
                Cancel Run
              </button>
            )}

            <button
              type="submit"
              disabled={!isInputValid || isRunning}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                isInputValid && !isRunning
                  ? "bg-white text-black hover:bg-zinc-200"
                  : "bg-zinc-900 text-zinc-600 cursor-not-allowed opacity-50 border border-zinc-800"
              }`}
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-black" />
                  <span>Executing Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="w-3 h-3 fill-current" />
                  <span>Run Investigation</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Active Pipeline Feedback */}
      {isRunning && (
        <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold text-white">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-400" />
              <span>Pipeline Execution in Progress</span>
            </div>
            <span className="text-[10px] uppercase font-mono bg-zinc-950 text-zinc-300 border border-zinc-800 px-2 py-0.5 rounded font-bold">
              {currentPhase || "EXECUTING"}
            </span>
          </div>
          {activitySummary && (
            <p className="text-xs text-zinc-300 font-normal leading-relaxed">
              {activitySummary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
