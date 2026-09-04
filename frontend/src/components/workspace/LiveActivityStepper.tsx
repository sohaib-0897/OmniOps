"use client";

import React, { useState } from "react";
import { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Loader2,
  Terminal,
  FileSearch,
  Database,
  Calculator,
  Compass,
  ChevronDown,
  ChevronRight,
  ListTodo,
  Bookmark,
  History,
  Cpu,
  ShieldCheck,
} from "lucide-react";

interface Props {
  streamState: InvestigationStreamState;
  onCancel: () => void;
}

export function LiveActivityStepper({ streamState, onCancel }: Props) {
  const isRunning = ["planning", "running", "verifying", "synthesizing"].includes(streamState.status);

  const [subGoalsOpen, setSubGoalsOpen] = useState(true);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [logsOpen, setLogsOpen] = useState(false);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "planning":
        return (
          <span className="bg-zinc-900 text-white border border-zinc-700 px-2 py-0.5 rounded text-[10px] font-bold font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
            PLANNING
          </span>
        );
      case "running":
        return (
          <span className="bg-zinc-900 text-white border border-zinc-700 px-2 py-0.5 rounded text-[10px] font-bold font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
            EXECUTING
          </span>
        );
      case "verifying":
        return (
          <span className="bg-zinc-900 text-white border border-zinc-700 px-2 py-0.5 rounded text-[10px] font-bold font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
            VERIFYING
          </span>
        );
      case "synthesizing":
        return (
          <span className="bg-zinc-900 text-white border border-zinc-700 px-2 py-0.5 rounded text-[10px] font-bold font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
            SYNTHESIZING
          </span>
        );
      case "completed":
        return (
          <span className="bg-zinc-900 text-zinc-200 border border-zinc-750 px-2 py-0.5 rounded text-[10px] font-bold font-mono flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-white" />
            COMPLETED
          </span>
        );
      case "cancelled":
        return <span className="bg-zinc-900 text-zinc-400 border border-zinc-800 px-2 py-0.5 rounded text-[10px] font-mono">CANCELLED</span>;
      case "failed":
        return <span className="bg-zinc-900 text-zinc-300 border border-zinc-700 px-2 py-0.5 rounded text-[10px] font-mono font-bold">FAILED</span>;
      default:
        return (
          <span className="bg-zinc-950 text-zinc-500 border border-zinc-850 px-2 py-0.5 rounded text-[10px] font-mono font-medium flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-400" />
            STANDBY
          </span>
        );
    }
  };

  const getToolIcon = (toolName?: string) => {
    if (!toolName) return <Terminal className="w-3.5 h-3.5 text-zinc-400" />;
    if (toolName.includes("sql") || toolName.includes("duckdb")) return <Database className="w-3.5 h-3.5 text-zinc-300" />;
    if (toolName.includes("search") || toolName.includes("retriev")) return <FileSearch className="w-3.5 h-3.5 text-zinc-300" />;
    if (toolName.includes("python") || toolName.includes("sandbox")) return <Calculator className="w-3.5 h-3.5 text-zinc-300" />;
    return <Compass className="w-3.5 h-3.5 text-zinc-300" />;
  };

  return (
    <div className="border border-zinc-800 bg-zinc-950 rounded-2xl p-4 space-y-4 shadow-xl font-sans">
      {/* 1. Header */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-850">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-zinc-400" />
          <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
            Execution Trace & Audit
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {getStatusBadge(streamState.status)}
          {isRunning && (
            <button
              type="button"
              onClick={onCancel}
              className="text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 px-2.5 py-0.5 rounded border border-zinc-700 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* 2. Active Activity Summary or Standby */}
      {streamState.activitySummary ? (
        <div className="flex items-start gap-3 p-3 rounded-xl bg-zinc-900 border border-zinc-800">
          {isRunning ? (
            <Loader2 className="w-4 h-4 text-zinc-300 animate-spin shrink-0 mt-0.5" />
          ) : streamState.status === "completed" ? (
            <CheckCircle2 className="w-4 h-4 text-white shrink-0 mt-0.5" />
          ) : streamState.status === "cancelled" ? (
            <XCircle className="w-4 h-4 text-zinc-500 shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <p className="text-xs font-medium text-zinc-200 leading-relaxed font-sans">
              {streamState.activitySummary}
            </p>
          </div>
        </div>
      ) : (
        <div className="p-3 rounded-xl bg-zinc-900/50 border border-zinc-850 space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-zinc-300 uppercase tracking-wider text-[10px] flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-zinc-400" />
              Compute Architecture
            </span>
            <span className="text-[10px] font-mono text-zinc-400 font-bold bg-zinc-900 px-1.5 py-0.5 rounded border border-zinc-800">
              Ready
            </span>
          </div>

          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="flex items-center gap-2">
                <Database className="w-3.5 h-3.5 text-zinc-400" />
                <span className="text-zinc-300 font-medium">DuckDB Vectorized Engine</span>
              </div>
              <span className="text-[10px] font-mono text-zinc-500">In-Memory</span>
            </div>

            <div className="flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="flex items-center gap-2">
                <FileSearch className="w-3.5 h-3.5 text-zinc-400" />
                <span className="text-zinc-300 font-medium">pgvector + PostgreSQL FTS RRF</span>
              </div>
              <span className="text-[10px] font-mono text-zinc-500">Production · k=60</span>
            </div>

            <div className="flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-3.5 h-3.5 text-zinc-400" />
                <span className="text-zinc-300 font-medium">Validated Evidence References</span>
              </div>
              <span className="text-[10px] font-mono text-zinc-500">SHA-256</span>
            </div>
          </div>
        </div>
      )}

      {/* 3. Sub-Tasks */}
      {streamState.planTasks.length > 0 && (
        <div className="space-y-2 pt-1">
          <button
            type="button"
            onClick={() => setSubGoalsOpen(!subGoalsOpen)}
            className="w-full flex items-center justify-between text-xs font-bold text-zinc-300 hover:text-white transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-1.5 uppercase tracking-wider text-xs">
              <ListTodo className="w-3.5 h-3.5 text-zinc-400" />
              Investigation Sub-Tasks ({streamState.planTasks.length})
            </span>
            {subGoalsOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </button>

          {subGoalsOpen && (
            <div className="space-y-1.5 pt-1">
              {streamState.planTasks.map((task) => (
                <div
                  key={task.id}
                  className={`flex items-center justify-between p-2.5 rounded-xl text-xs border transition-colors ${
                    task.status === "in_progress"
                      ? "bg-zinc-900 border-zinc-700 text-white font-semibold"
                      : task.status === "completed"
                      ? "bg-zinc-950 border-zinc-800 text-zinc-300"
                      : "bg-zinc-950 border-zinc-850 text-zinc-600"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-mono text-xs shrink-0 font-bold">{task.id}</span>
                    <span className="truncate">{task.title}</span>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 shrink-0 font-semibold text-zinc-400">
                    {task.target_modality}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 4. Live Discovered Evidence Feed */}
      {streamState.evidenceDiscovered.length > 0 && (
        <div className="space-y-2 pt-1">
          <button
            type="button"
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="w-full flex items-center justify-between text-xs font-bold text-zinc-300 hover:text-white transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-1.5 uppercase tracking-wider text-xs">
              <Bookmark className="w-3.5 h-3.5 text-zinc-400" />
              Retrieved Excerpts ({streamState.evidenceDiscovered.length})
            </span>
            {evidenceOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </button>

          {evidenceOpen && (
            <div className="space-y-2 pt-1 max-h-52 overflow-y-auto pr-1">
              {streamState.evidenceDiscovered.map((ev, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between text-xs text-zinc-400 font-medium">
                    <span className="text-white font-bold truncate max-w-[160px]">{ev.source_name}</span>
                    <span className="uppercase font-mono text-[9px] bg-zinc-950 border border-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded font-semibold">{ev.modality}</span>
                  </div>
                  <p className="text-xs text-zinc-300 italic line-clamp-2 leading-relaxed">
                    &ldquo;{ev.quote}&rdquo;
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5. Execution Step Trace Log */}
      {streamState.steps.length > 0 && (
        <div className="space-y-2 pt-1">
          <button
            type="button"
            onClick={() => setLogsOpen(!logsOpen)}
            className="w-full flex items-center justify-between text-xs font-bold text-zinc-300 hover:text-white transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-1.5 uppercase tracking-wider text-xs">
              <History className="w-3.5 h-3.5 text-zinc-400" />
              Execution Trace ({streamState.steps.length} Steps)
            </span>
            {logsOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </button>

          {logsOpen && (
            <div className="space-y-1.5 pt-1 max-h-60 overflow-y-auto pr-1 font-mono">
              {streamState.steps.map((step) => (
                <div
                  key={step.step_number}
                  className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 text-xs space-y-1"
                >
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5 font-semibold text-zinc-200">
                      {getToolIcon(step.tool_name)}
                      <span>Step {step.step_number}</span>
                      <span className="text-zinc-500 font-normal capitalize font-sans">({step.step_type})</span>
                    </div>
                    <span className="text-zinc-400 text-[10px]">{step.duration_ms}ms</span>
                  </div>
                  <p className="text-xs text-zinc-400 font-sans line-clamp-2 leading-snug">{step.user_activity_summary}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
