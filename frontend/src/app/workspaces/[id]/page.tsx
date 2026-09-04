"use client";

import React, { useState, useEffect } from "react";
import { useWorkspaceData } from "@/hooks/useWorkspaceData";
import { useInvestigationStream } from "@/hooks/useInvestigationStream";
import { apiClient } from "@/lib/api-client";
import {
  SourceDocument,
  TabularDataset,
  EpistemicClaim,
  InvestigationSession,
  EvidenceLineageGraph,
} from "@/types/api";

import { WorkspaceHeader } from "@/components/workspace/WorkspaceHeader";
import { FileUploadZone } from "@/components/workspace/FileUploadZone";
import { SourceDataCatalog } from "@/components/workspace/SourceDataCatalog";
import { ObjectiveInput } from "@/components/workspace/ObjectiveInput";
import { ExecutiveReportView } from "@/components/workspace/ExecutiveReportView";
import { LiveActivityStepper } from "@/components/workspace/LiveActivityStepper";
import { EvidenceLineageDrawer } from "@/components/workspace/EvidenceLineageDrawer";
import { TabularPreviewModal } from "@/components/workspace/TabularPreviewModal";
import { SourcePreviewModal } from "@/components/workspace/SourcePreviewModal";
import {
  Loader2,
  Activity,
  Compass,
  Database,
  ArrowRight,
  TrendingUp,
  FileSearch,
  Calculator,
  Layers,
  ShieldCheck,
} from "lucide-react";

type MobileTab = "sources" | "investigation" | "telemetry";

const EXAMPLE_PLAYBOOKS = [
  {
    title: "Segment Profit Margin & Churn Correlation",
    description: "Executes DuckDB SQL across customer datasets to calculate segment margin variance and verify contract terms.",
    query: "Compute customer churn variance across product segments and identify primary operational margin risk factors.",
    icon: TrendingUp,
    modality: "XLSX + CSV",
  },
  {
    title: "Supplier Invoices vs Transcript Audit",
    description: "Cross-references vendor billing spreadsheets with executive meeting audio transcripts to detect unapproved rate hikes.",
    query: "Cross-reference supplier invoice spreadsheets with recent executive meeting transcripts to find pricing discrepancies.",
    icon: FileSearch,
    modality: "PDF + Audio",
  },
  {
    title: "Q3 Revenue Decline Root Cause Synthesis",
    description: "Performs full multi-source synthesis, computing exact revenue delta and formulating actionable strategic recovery items.",
    query: "Analyze why enterprise software revenue declined in Q3, compute segment margin variance, and synthesize strategic actions.",
    icon: Calculator,
    modality: "Multi-Modal",
  },
];

export default function WorkspaceDashboard({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = React.use(params);
  const workspaceId = resolvedParams.id;

  const { workspace, files, tables, isLoading, mutateAll } = useWorkspaceData(workspaceId);
  const [activeInvestigationId, setActiveInvestigationId] = useState<string | null>(null);
  const { state: streamState, cancel: cancelInvestigation } = useInvestigationStream(activeInvestigationId);

  const [activeTab, setActiveTab] = useState<MobileTab>("investigation");
  const [lineageGraph, setLineageGraph] = useState<EvidenceLineageGraph | null>(null);

  const [previewFile, setPreviewFile] = useState<SourceDocument | null>(null);
  const [previewTable, setPreviewTable] = useState<TabularDataset | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<EpistemicClaim | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);

  useEffect(() => {
    if (activeInvestigationId && (streamState.status === "completed" || selectedClaim || selectedCitationId)) {
      apiClient
        .get<EvidenceLineageGraph>(`/investigations/${activeInvestigationId}/evidence`)
        .then((data) => setLineageGraph(data))
        .catch((err) => console.error("Failed to load lineage graph:", err));
    }
  }, [activeInvestigationId, streamState.status, selectedClaim, selectedCitationId]);

  const handleStartInvestigation = async (objective: string, maxSteps: number) => {
    try {
      setLineageGraph(null);
      const session = await apiClient.post<InvestigationSession>(
        `/workspaces/${workspaceId}/investigations`,
        { objective, max_steps: maxSteps }
      );
      setActiveInvestigationId(session.id);
      setActiveTab("investigation");
    } catch (err) {
      console.error("Failed to start investigation:", err);
    }
  };

  const isRunning = ["planning", "running", "verifying", "synthesizing"].includes(streamState.status);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center gap-3 text-zinc-500 text-xs">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
        <span>Loading workspace data...</span>
      </div>
    );
  }

  const totalSourceCount = (files?.length || 0) + (tables?.length || 0);

  return (
    <div className="min-h-screen bg-black text-zinc-100 flex flex-col justify-between relative overflow-hidden font-sans selection:bg-zinc-800 selection:text-white">
      {/* Global Header */}
      <WorkspaceHeader
        workspace={workspace}
        onNewInvestigation={() => {
          setActiveInvestigationId(null);
          setLineageGraph(null);
        }}
      />

      {/* Segmented Tab Control for Mobile/Tablet */}
      <div className="lg:hidden border-b border-zinc-850 bg-zinc-950 p-2 flex items-center justify-around text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("sources")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all ${
            activeTab === "sources"
              ? "bg-white text-black"
              : "text-zinc-400 hover:text-white"
          }`}
        >
          <Database className="w-3.5 h-3.5" />
          <span>Sources ({totalSourceCount})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("investigation")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all ${
            activeTab === "investigation"
              ? "bg-white text-black"
              : "text-zinc-400 hover:text-white"
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Investigation</span>
          {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-ping" />}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("telemetry")}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all ${
            activeTab === "telemetry"
              ? "bg-white text-black"
              : "text-zinc-400 hover:text-white"
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Trace ({streamState.steps.length})</span>
        </button>
      </div>

      {/* Tripartite Layout */}
      <div className="flex-1 grid grid-cols-12 overflow-hidden z-10">
        {/* LEFT PANEL: Data Catalog */}
        <aside
          className={`col-span-12 lg:col-span-3 border-r border-zinc-850 p-4 sm:p-5 bg-zinc-950 overflow-y-auto max-h-[calc(100vh-65px)] space-y-5 ${
            activeTab === "sources" ? "block" : "hidden lg:block"
          }`}
        >
          <FileUploadZone workspaceId={workspaceId} onUploadComplete={mutateAll} />
          <SourceDataCatalog
            workspaceId={workspaceId}
            files={files || []}
            tables={tables || []}
            onRefresh={mutateAll}
            onPreviewFile={(f) => setPreviewFile(f)}
            onPreviewTable={(t) => setPreviewTable(t)}
          />
        </aside>

        {/* CENTER PANEL: Investigation & Report */}
        <main
          className={`col-span-12 lg:col-span-6 p-4 sm:p-6 lg:p-7 overflow-y-auto max-h-[calc(100vh-65px)] space-y-5 bg-black ${
            activeTab === "investigation" ? "block" : "hidden lg:block"
          }`}
        >
          <ObjectiveInput
            onStartInvestigation={handleStartInvestigation}
            onCancel={cancelInvestigation}
            isRunning={isRunning}
            currentPhase={streamState.status}
            activitySummary={streamState.activitySummary}
          />

          {isRunning ? (
            <div className="border border-zinc-800 rounded-2xl p-6 bg-zinc-950 space-y-4 text-center">
              <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center mx-auto">
                <Compass className="w-5 h-5 animate-spin" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm sm:text-base font-bold text-white tracking-tight">
                  Evidence-Grounded Multi-Source Investigation in Progress
                </h3>
                <p className="text-xs text-zinc-400 max-w-md mx-auto leading-relaxed">
                  Executing analytical DAG, computing metrics in DuckDB, and verifying claims against primary sources.
                </p>
              </div>

              {/* Progress Stage Cards */}
              <div className="grid grid-cols-3 gap-2.5 max-w-md mx-auto text-xs pt-1">
                <div className={`p-3 rounded-xl border text-left transition-all ${
                  ["planning", "running", "verifying", "synthesizing"].includes(streamState.status)
                    ? "bg-zinc-900 border-zinc-700 text-white font-bold"
                    : "bg-zinc-950 border-zinc-850 text-zinc-600"
                }`}>
                  <span className="text-[9px] uppercase font-bold block text-zinc-400">Stage 1</span>
                  <span>Planning DAG</span>
                </div>
                <div className={`p-3 rounded-xl border text-left transition-all ${
                  ["running", "verifying", "synthesizing"].includes(streamState.status)
                    ? "bg-zinc-900 border-zinc-700 text-white font-bold"
                    : "bg-zinc-950 border-zinc-850 text-zinc-600"
                }`}>
                  <span className="text-[9px] uppercase font-bold block text-zinc-400">Stage 2</span>
                  <span>Execution</span>
                </div>
                <div className={`p-3 rounded-xl border text-left transition-all ${
                  ["verifying", "synthesizing"].includes(streamState.status)
                    ? "bg-zinc-900 border-zinc-700 text-white font-bold"
                    : "bg-zinc-950 border-zinc-850 text-zinc-600"
                }`}>
                  <span className="text-[9px] uppercase font-bold block text-zinc-400">Stage 3</span>
                  <span>Synthesis</span>
                </div>
              </div>
            </div>
          ) : streamState.finalResponse ? (
            <ExecutiveReportView
              report={streamState.finalResponse}
              onInspectClaim={(claim) => {
                setSelectedClaim(claim);
                setSelectedCitationId(null);
              }}
              onInspectCitation={(citId) => {
                setSelectedCitationId(citId);
              }}
            />
          ) : (
            /* Playbooks & Workflow Guide */
            <div className="border border-zinc-800 bg-zinc-950 rounded-2xl p-5 sm:p-6 space-y-5">
              <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-zinc-850">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center font-bold">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white tracking-tight">
                      Analytical Playbooks
                    </h3>
                    <p className="text-xs text-zinc-400">
                      Select an example playbook or submit your custom query above
                    </p>
                  </div>
                </div>
                <span className="text-[10px] text-zinc-400 font-mono font-bold bg-zinc-900 border border-zinc-800 px-2.5 py-0.5 rounded">
                  Evidence Referenced
                </span>
              </div>

              {/* Playbook Cards Grid */}
              <div className="grid sm:grid-cols-3 gap-3">
                {EXAMPLE_PLAYBOOKS.map((playbook, idx) => {
                  const Icon = playbook.icon;
                  return (
                    <div
                      key={idx}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleStartInvestigation(playbook.query, 10)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleStartInvestigation(playbook.query, 10);
                        }
                      }}
                      className="group p-4 rounded-xl border border-zinc-850 bg-zinc-900/50 hover:bg-zinc-900 hover:border-zinc-700 cursor-pointer transition-all flex flex-col justify-between space-y-3 text-left outline-none focus-visible:ring-1 focus-visible:ring-zinc-400"
                    >
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="w-7 h-7 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-400 flex items-center justify-center group-hover:text-white transition-colors">
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border border-zinc-800 bg-zinc-950 text-zinc-400">
                            {playbook.modality}
                          </span>
                        </div>
                        <h4 className="text-xs font-bold text-zinc-200 group-hover:text-white transition-colors leading-snug">
                          {playbook.title}
                        </h4>
                        <p className="text-[11px] text-zinc-400 line-clamp-2 leading-relaxed">
                          {playbook.description}
                        </p>
                      </div>

                      <div className="pt-2 border-t border-zinc-850 flex items-center justify-between text-xs font-bold text-zinc-300 group-hover:text-white">
                        <span>Run</span>
                        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 3-Step Workflow Strip */}
              <div className="p-3 rounded-xl bg-zinc-900/50 border border-zinc-850 grid sm:grid-cols-3 gap-3 text-xs">
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded bg-zinc-800 text-zinc-300 font-bold font-mono text-[10px] flex items-center justify-center shrink-0 border border-zinc-700">
                    1
                  </div>
                  <span className="text-zinc-300 font-semibold">Data Ingestion</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded bg-zinc-800 text-zinc-300 font-bold font-mono text-[10px] flex items-center justify-center shrink-0 border border-zinc-700">
                    2
                  </div>
                  <span className="text-zinc-300 font-semibold">DAG Execution</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded bg-zinc-800 text-zinc-300 font-bold font-mono text-[10px] flex items-center justify-center shrink-0 border border-zinc-700">
                    3
                  </div>
                  <span className="text-zinc-300 font-semibold">Lineage Verification</span>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* RIGHT PANEL: Stepper & Telemetry */}
        <aside
          className={`col-span-12 lg:col-span-3 border-l border-zinc-850 p-4 sm:p-5 bg-zinc-950 overflow-y-auto max-h-[calc(100vh-65px)] space-y-4 ${
            activeTab === "telemetry" ? "block" : "hidden lg:block"
          }`}
        >
          <LiveActivityStepper
            streamState={streamState}
            onCancel={cancelInvestigation}
          />
        </aside>
      </div>

      {/* MODALS & DRAWERS */}
      <TabularPreviewModal
        table={previewTable}
        onClose={() => setPreviewTable(null)}
      />
      <SourcePreviewModal
        file={previewFile}
        onClose={() => setPreviewFile(null)}
      />
      <EvidenceLineageDrawer
        claim={selectedClaim}
        citationId={selectedCitationId}
        lineageGraph={lineageGraph}
        onClose={() => {
          setSelectedClaim(null);
          setSelectedCitationId(null);
        }}
      />
    </div>
  );
}
