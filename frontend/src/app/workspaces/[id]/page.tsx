"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Files, Plus } from "lucide-react";
import { useWorkspaceData } from "@/hooks/useWorkspaceData";
import { useInvestigationStream } from "@/hooks/useInvestigationStream";
import { apiClient } from "@/lib/api-client";
import type {
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
import { ConversationReport } from "@/components/workspace/ConversationReport";
import { ExecutiveReportView } from "@/components/workspace/ExecutiveReportView";
import { InvestigationProgress } from "@/components/workspace/InvestigationProgress";
import { LiveActivityStepper } from "@/components/workspace/LiveActivityStepper";
import { EvidenceLineageDrawer } from "@/components/workspace/EvidenceLineageDrawer";
import { TabularPreviewModal } from "@/components/workspace/TabularPreviewModal";
import { SourcePreviewModal } from "@/components/workspace/SourcePreviewModal";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorState, LoadingState, StatusBadge } from "@/components/ui/Primitives";

const activeRuntimeStates = [
  "created",
  "planning",
  "ready",
  "running",
  "executing",
  "observing",
  "verifying",
  "replanning",
  "synthesizing",
];

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = React.use(params);
  return <Workspace key={id} workspaceId={id} />;
}

function SourcesPanel({
  workspaceId,
  files,
  tables,
  onRefresh,
  onPreviewFile,
  onPreviewTable,
}: {
  workspaceId: string;
  files: SourceDocument[];
  tables: TabularDataset[];
  onRefresh: () => void;
  onPreviewFile: (file: SourceDocument) => void;
  onPreviewTable: (table: TabularDataset) => void;
}) {
  return (
    <div className="space-y-6">
      <FileUploadZone workspaceId={workspaceId} onUploadComplete={onRefresh} compact={files.length > 0} />
      <div className="border-t border-zinc-800 pt-5">
        <SourceDataCatalog
          workspaceId={workspaceId}
          files={files}
          tables={tables}
          onRefresh={onRefresh}
          onPreviewFile={onPreviewFile}
          onPreviewTable={onPreviewTable}
        />
      </div>
    </div>
  );
}

function Workspace({ workspaceId }: { workspaceId: string }) {
  const { workspace, files, tables, isLoading, isError, mutateAll } =
    useWorkspaceData(workspaceId);
  const [activeId, setActiveId] = useState<string | null>(null);
  const { state, cancel } = useInvestigationStream(activeId);
  const [lineage, setLineage] = useState<EvidenceLineageGraph | null>(null);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [previewFile, setPreviewFile] = useState<SourceDocument | null>(null);
  const [previewTable, setPreviewTable] = useState<TabularDataset | null>(null);
  const [claim, setClaim] = useState<EpistemicClaim | null>(null);
  const [citation, setCitation] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [fullAnalysisOpen, setFullAnalysisOpen] = useState(false);
  const submission = useRef(false);

  useEffect(() => {
    const sync = () =>
      setActiveId(
        new URLSearchParams(window.location.search).get("investigation"),
      );
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const selectInvestigation = (id: string | null) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("investigation", id);
    else url.searchParams.delete("investigation");
    window.history.pushState(null, "", url.pathname + url.search);
    setActiveId(id);
  };

  const fetchLineage = useCallback(async () => {
    if (!activeId) return;
    setLineageLoading(true);
    setLineageError(null);
    try {
      setLineage(
        await apiClient.get<EvidenceLineageGraph>(
          `/investigations/${activeId}/evidence`,
        ),
      );
    } catch (error) {
      setLineageError(
        error instanceof Error
          ? error.message
          : "Provenance could not be loaded.",
      );
    } finally {
      setLineageLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    setLineage(null);
    setClaim(null);
    setCitation(null);
    setFullAnalysisOpen(false);
  }, [activeId]);

  useEffect(() => {
    if (activeId && ["completed", "failed", "cancelled"].includes(state.status))
      void fetchLineage();
  }, [activeId, state.status, fetchLineage]);

  const start = async (objective: string, maxSteps: number) => {
    if (submission.current) return false;
    submission.current = true;
    setSubmitting(true);
    setStartError(null);
    try {
      const session = await apiClient.post<InvestigationSession>(
        `/workspaces/${workspaceId}/investigations`,
        { objective, max_steps: maxSteps },
      );
      selectInvestigation(session.id);
      return true;
    } catch (error) {
      setStartError(
        error instanceof Error
          ? error.message
          : "Investigation could not be started.",
      );
      return false;
    } finally {
      submission.current = false;
      setSubmitting(false);
    }
  };

  const running = activeRuntimeStates.includes(state.status);
  const terminal = ["completed", "failed", "cancelled"].includes(state.status);
  const newInvestigation = () => {
    selectInvestigation(null);
    setStartError(null);
  };
  const readyCount = files.filter((file) =>
    file.processing_status === "ready",
  ).length;
  const verifiedClaimCount =
    state.finalResponse?.claims.filter(
      (item) => item.verification_status === "VERIFIED",
    ).length ?? null;
  const reportSourceCount = lineage
    ? new Set(
        lineage.nodes
          .filter((node) => node.type === "source")
          .map((node) => node.id),
      ).size
    : null;

  if (isLoading)
    return (
      <main id="main-content" className="app-container py-8">
        <LoadingState label="Loading workspace" />
      </main>
    );

  if (!workspace)
    return (
      <main id="main-content" className="app-container max-w-2xl space-y-5 py-8">
        <Link href="/" className="btn-ghost">
          <ArrowLeft className="h-4 w-4" />
          All workspaces
        </Link>
        <ErrorState
          title="Workspace unavailable"
          message="The workspace could not be loaded. Check your access or try again."
          onRetry={mutateAll}
        />
      </main>
    );

  const sourcesPanel = (
    <SourcesPanel
      workspaceId={workspaceId}
      files={files}
      tables={tables}
      onRefresh={mutateAll}
      onPreviewFile={setPreviewFile}
      onPreviewTable={setPreviewTable}
    />
  );

  return (
    <div className="app-page intelligence-workspace min-h-dvh">
      <WorkspaceHeader
        workspace={workspace}
        onNewInvestigation={running ? undefined : newInvestigation}
        onSources={() => setSourcesOpen(true)}
        onActivity={activeId ? () => setActivityOpen(true) : undefined}
        onToggleNavigation={() => setNavigationOpen((open) => !open)}
        navigationOpen={navigationOpen}
        sourceCount={files.length}
      />

      <div className={`chat-workspace-shell ${navigationOpen ? "" : "navigation-collapsed"}`}>
        <aside id="workspace-navigation" className={`workspace-navigation ${navigationOpen ? "hidden lg:block" : "hidden"}`} aria-label="Workspace navigation">
          <div className="flex h-[calc(100dvh-4rem)] flex-col overflow-y-auto p-4">
            <button
              type="button"
              onClick={newInvestigation}
              disabled={running}
              className="navigation-new btn-ghost w-full justify-start text-zinc-200"
            >
              <Plus className="h-4 w-4" />
              New analysis
            </button>
            {activeId && <div className="mt-8 px-3">
              <p className="type-label text-zinc-400">Current investigation</p>
              {activeId ? (
                <div className="mt-3">
                  <p className="line-clamp-2 text-xs leading-5 text-zinc-300">
                    {state.objective || "Loading investigation…"}
                  </p>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <StatusBadge status={state.status} />
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-xs leading-5 text-zinc-500">
                  No investigation selected.
                </p>
              )}
            </div>}
            <div className="mt-8 px-1">
              <button className="btn-ghost w-full justify-start" onClick={() => setSourcesOpen(true)}><Files className="h-4 w-4" /> Workspace sources <span className="ml-auto text-xs">{files.length}</span></button>
            </div>
            <Link href="/" className="btn-ghost mt-auto justify-start"><ArrowLeft className="h-4 w-4" /> All workspaces</Link>
          </div>
        </aside>

        <main id="main-content" className="min-w-0">
          <div className="conversation-column">

            {isError && (
              <div className="mb-5">
                <ErrorState
                  title="Some workspace data is unavailable"
                  message="Source counts may be incomplete. Retry to reload the workspace."
                  onRetry={mutateAll}
                />
              </div>
            )}

            {!activeId ? (
              <div className="workspace-empty-state flex flex-1 items-center">
                <div className="w-full">
                  <ObjectiveInput
                    workspaceId={workspaceId}
                    onStartInvestigation={start}
                    onSourcesChanged={mutateAll}
                    submitting={submitting}
                    sourceCount={files.length}
                    readySourceCount={readyCount}
                    onInspectSources={() => setSourcesOpen(true)}
                  />
                  {startError && (
                    <div className="mx-auto mt-4 max-w-2xl">
                      <ErrorState
                        title="Could not start investigation"
                        message={startError}
                      />
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-1 flex-col">
                <section className="conversation-user-message" aria-labelledby="question-label">
                  <p id="question-label" className="type-label mb-2 text-zinc-400">
                    Your question
                  </p>
                  <p className="whitespace-pre-wrap text-[15px] leading-7 text-zinc-200">
                    {state.objective || "Loading investigation question…"}
                  </p>
                </section>

                <section className="conversation-assistant-message" aria-label="OmniOps response">
                  {!state.finalResponse && <p className="response-byline">OmniOps <span>Investigation</span></p>}
                  <InvestigationProgress
                    streamState={state}
                    sourceCount={state.status === "completed" ? reportSourceCount : null}
                    verifiedClaimCount={
                      state.status === "completed" ? verifiedClaimCount : null
                    }
                    onCancel={running ? () => void cancel() : undefined}
                    onRetry={
                      state.status === "failed" && state.objective
                        ? () => void start(state.objective, 12)
                        : undefined
                    }
                    onViewTechnical={() => setActivityOpen(true)}
                  />

                  {state.errorMessage && state.status !== "failed" && (
                    <div className="mt-5">
                      <ErrorState title="Runtime notice" message={state.errorMessage} />
                    </div>
                  )}

                  {state.finalResponse && (
                    <div className="mt-5">
                      <ConversationReport
                        report={state.finalResponse}
                        onInspectClaim={(item) => {
                          setClaim(item);
                          setCitation(null);
                        }}
                        onInspectCitation={(id) => {
                          setCitation(id);
                          setClaim(null);
                        }}
                        onViewFullAnalysis={() =>
                          setFullAnalysisOpen((open) => !open)
                        }
                        fullAnalysisOpen={fullAnalysisOpen}
                      />
                      {fullAnalysisOpen && (
                        <section
                          id="full-analysis"
                          className="full-analysis-enter mt-12 border-t border-zinc-700 pt-9"
                          aria-label="Full analysis"
                        >
                          <div className="mb-7">
                            <p className="eyebrow">Structured report</p>
                            <h2 className="mt-2 text-xl font-semibold tracking-tight">
                              Full analysis
                            </h2>
                          </div>
                          <ExecutiveReportView
                            report={state.finalResponse}
                            onInspectClaim={(item) => {
                              setClaim(item);
                              setCitation(null);
                            }}
                            onInspectCitation={(id) => {
                              setCitation(id);
                              setClaim(null);
                            }}
                          />
                        </section>
                      )}
                    </div>
                  )}
                </section>

                {terminal && (
                  <details className="followup-dock" onToggle={(event) => { if (event.currentTarget.open) event.currentTarget.querySelector("textarea")?.focus(); }}>
                    <summary className="flex items-center justify-between gap-3"><span>Ask another question</span><ArrowUpRight className="h-4 w-4" /></summary>
                    <div className="pt-4">
                    <ObjectiveInput
                      workspaceId={workspaceId}
                      onStartInvestigation={start}
                      onSourcesChanged={mutateAll}
                      submitting={submitting}
                      variant="another"
                      sourceCount={files.length}
                      readySourceCount={readyCount}
                      onInspectSources={() => setSourcesOpen(true)}
                    />
                    {startError && (
                      <div className="mt-4">
                        <ErrorState
                          title="Could not start investigation"
                          message={startError}
                        />
                      </div>
                    )}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </main>

      </div>

      <Dialog
        open={sourcesOpen}
        onClose={() => setSourcesOpen(false)}
        title="Workspace sources"
        description="Upload, inspect, and manage source material."
        drawer
      >
        {sourcesPanel}
      </Dialog>
      <Dialog
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        title="Investigation activity"
        description="Persisted operational events and advanced runtime details."
        drawer
      >
        <LiveActivityStepper streamState={state} onCancel={() => void cancel()} />
      </Dialog>
      <TabularPreviewModal table={previewTable} onClose={() => setPreviewTable(null)} />
      <SourcePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
      <EvidenceLineageDrawer
        claim={claim}
        citationId={citation}
        lineageGraph={lineage}
        loading={lineageLoading}
        error={lineageError}
        onRetry={() => void fetchLineage()}
        onClose={() => {
          setClaim(null);
          setCitation(null);
        }}
        onInspectSource={(id) => {
          const file = files.find((item) => item.id === id);
          if (file) {
            setClaim(null);
            setCitation(null);
            setPreviewFile(file);
          } else {
            setLineageError(
              "This source is no longer available in the workspace catalog.",
            );
          }
        }}
      />
    </div>
  );
}
