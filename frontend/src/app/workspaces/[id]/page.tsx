"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Database, FileText, ArrowLeft } from "lucide-react";
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
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "@/components/ui/Primitives";

type Tab = "sources" | "investigation" | "trace";
const runtimeStates = [
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
function Workspace({ workspaceId }: { workspaceId: string }) {
  const { workspace, files, tables, isLoading, isError, mutateAll } =
    useWorkspaceData(workspaceId);
  const [activeId, setActiveId] = useState<string | null>(null);
  const { state, cancel } = useInvestigationStream(activeId);
  const [tab, setTab] = useState<Tab>("investigation");
  const [lineage, setLineage] = useState<EvidenceLineageGraph | null>(null);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [previewFile, setPreviewFile] = useState<SourceDocument | null>(null);
  const [previewTable, setPreviewTable] = useState<TabularDataset | null>(null);
  const [claim, setClaim] = useState<EpistemicClaim | null>(null);
  const [citation, setCitation] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
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
    } catch (err) {
      setLineageError(
        err instanceof Error ? err.message : "Provenance could not be loaded.",
      );
    } finally {
      setLineageLoading(false);
    }
  }, [activeId]);
  useEffect(() => {
    setLineage(null);
    setClaim(null);
    setCitation(null);
  }, [activeId]);
  useEffect(() => {
    if (activeId && ["completed", "failed", "cancelled"].includes(state.status))
      void fetchLineage();
  }, [activeId, state.status, fetchLineage]);
  const start = async (objective: string, maxSteps: number) => {
    if (submission.current) return;
    submission.current = true;
    setSubmitting(true);
    setStartError(null);
    try {
      const session = await apiClient.post<InvestigationSession>(
        `/workspaces/${workspaceId}/investigations`,
        { objective, max_steps: maxSteps },
      );
      selectInvestigation(session.id);
      setTab("investigation");
    } catch (err) {
      setStartError(
        err instanceof Error
          ? err.message
          : "Investigation could not be started.",
      );
    } finally {
      submission.current = false;
      setSubmitting(false);
    }
  };
  const running = runtimeStates.includes(state.status);
  const newInvestigation = () => {
    selectInvestigation(null);
    setStartError(null);
    setTab("investigation");
  };
  const readyCount = files.filter((file) =>
    ["ready", "partially_ready"].includes(file.processing_status),
  ).length;
  if (isLoading)
    return (
      <main id="main-content" className="app-container py-8">
        <LoadingState label="Loading workspace" />
      </main>
    );
  if (!workspace)
    return (
      <main
        id="main-content"
        className="app-container max-w-2xl space-y-5 py-8"
      >
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
  return (
    <div className="app-page">
      <WorkspaceHeader
        workspace={workspace}
        onNewInvestigation={running ? undefined : newInvestigation}
      />
      <nav
        aria-label="Workspace panels"
        className="border-b border-zinc-800 bg-[#101113] min-[1440px]:hidden"
      >
        <div className="app-container flex gap-1">
          {(
            [
              {
                id: "sources",
                label: "Sources",
                count: files.length,
                icon: Database,
              },
              {
                id: "investigation",
                label: "Investigation",
                count: null,
                icon: FileText,
              },
              {
                id: "trace",
                label: "Trace",
                count: state.timeline.length,
                icon: Activity,
              },
            ] as const
          ).map(({ id, label, count, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              aria-current={tab === id ? "page" : undefined}
              aria-controls={`panel-${id}`}
              className={`flex min-h-11 flex-1 items-center justify-center gap-2 border-b-2 px-2 text-xs font-medium sm:flex-none sm:px-5 ${tab === id ? "border-zinc-100 text-zinc-100" : "border-transparent text-zinc-400 hover:text-white"} ${id === "sources" ? "lg:hidden" : ""}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
              {count != null && (
                <span className="text-[11px] text-zinc-400">{count}</span>
              )}
            </button>
          ))}
        </div>
      </nav>
      <main id="main-content" className="app-container workspace-grid">
        <aside
          id="panel-sources"
          aria-label="Workspace sources"
          className={`${tab === "sources" ? "block" : "hidden"} min-w-0 lg:block`}
        >
          <div className="space-y-5 lg:border-r lg:border-zinc-800 lg:pr-5">
            <FileUploadZone
              workspaceId={workspaceId}
              onUploadComplete={mutateAll}
            />
            <div className="border-t border-zinc-800 pt-5">
              <SourceDataCatalog
                workspaceId={workspaceId}
                files={files}
                tables={tables}
                onRefresh={mutateAll}
                onPreviewFile={setPreviewFile}
                onPreviewTable={setPreviewTable}
              />
            </div>
          </div>
        </aside>
        <section
          id="panel-investigation"
          aria-label="Investigation"
          className={`${tab === "investigation" ? "block" : "hidden"} min-w-0 ${tab === "sources" ? "lg:block" : ""} min-[1440px]:block`}
        >
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-zinc-400">
                {readyCount} of {files.length} sources ready or partially ready
              </p>
              {activeId && (
                <span className="mono-copy" title={activeId}>
                  Run {activeId.slice(0, 8)}
                </span>
              )}
            </div>
            {isError && (
              <ErrorState
                title="Some workspace data is unavailable"
                message="Source counts may be incomplete. Retry to reload the catalog."
                onRetry={mutateAll}
              />
            )}
            {activeId ? (
              <section className="surface p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="eyebrow">Investigation objective</p>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={state.status} />
                    {running && (
                      <button
                        className="btn-destructive"
                        onClick={() => void cancel()}
                      >
                        Cancel investigation
                      </button>
                    )}
                  </div>
                </div>
                <h1 className="mt-3 break-words text-base font-medium leading-7 text-zinc-200">
                  {state.objective || "Loading investigation"}
                </h1>
              </section>
            ) : (
              <ObjectiveInput
                onStartInvestigation={start}
                onCancel={cancel}
                isRunning={running}
                submitting={submitting}
              />
            )}
            {startError && (
              <ErrorState
                title="Could not start investigation"
                message={startError}
              />
            )}
            {state.errorMessage && (
              <ErrorState
                title={
                  state.status === "failed"
                    ? "Investigation failed"
                    : "Runtime notice"
                }
                message={state.errorMessage}
              />
            )}
            {state.finalResponse ? (
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
            ) : activeId ? (
              <section className="surface p-5">
                <div className="flex items-center gap-3">
                  <StatusBadge status={state.status} />
                  <h2 className="section-title">
                    {running
                      ? "Investigation in progress"
                      : state.status === "cancelled"
                        ? "Investigation cancelled"
                        : state.status === "failed"
                          ? "No final report produced"
                          : "No final report available"}
                  </h2>
                </div>
                <p className="body-copy mt-3">
                  {running
                    ? "Operational events appear in the trace as they are persisted. The report will appear here when synthesis completes."
                    : "Persisted operational history remains available in the trace."}
                </p>
                <button
                  className="btn-secondary mt-4 min-[1440px]:hidden"
                  onClick={() => setTab("trace")}
                >
                  View runtime trace
                </button>
              </section>
            ) : (
              <EmptyState
                title="Your findings will appear here"
                description="Upload relevant sources and run a focused investigation. Inspect each finding through its citations and recorded provenance."
              />
            )}
          </div>
        </section>
        <aside
          id="panel-trace"
          aria-label="Investigation trace"
          className={`${tab === "trace" ? "block" : "hidden"} min-w-0 min-[1440px]:block`}
        >
          <LiveActivityStepper streamState={state} onCancel={cancel} />
        </aside>
      </main>
      <TabularPreviewModal
        table={previewTable}
        onClose={() => setPreviewTable(null)}
      />
      <SourcePreviewModal
        file={previewFile}
        onClose={() => setPreviewFile(null)}
      />
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
          } else
            setLineageError(
              "This source is no longer available in the workspace catalog.",
            );
        }}
      />
    </div>
  );
}
