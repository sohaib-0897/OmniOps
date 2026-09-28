"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { motionTokens } from "@/motion/tokens";
import { useWorkspaceData } from "@/hooks/useWorkspaceData";
import { useInvestigationStream } from "@/hooks/useInvestigationStream";
import { useInvestigationHistory, useLineage, useOutlines } from "@/hooks/useCasefileData";
import { apiClient } from "@/lib/api-client";
import { buildBrief, indexLineage } from "@/lib/brief-model";
import { deriveInvestigationStage } from "@/lib/investigation-stages";
import type { FailureAction } from "@/lib/failure-copy";
import type { InvestigationSession, SourceDocument, TabularDataset } from "@/types/api";
import { ErrorState, LoadingState } from "@/components/ui/Primitives";
import { SourcePreviewModal } from "@/components/workspace/SourcePreviewModal";
import { TabularPreviewModal } from "@/components/workspace/TabularPreviewModal";
import { MobileBar, Rail, type WorkspaceView } from "@/components/casefile/Rail";
import { EmptyWorkspace } from "@/components/casefile/EmptyWorkspace";
import { InvestigationField, StageBar, formatClock, useElapsed, useStageDetail } from "@/components/casefile/InvestigationField";
import { Brief, type Selection } from "@/components/casefile/Brief";
import { Inspector, type InspectorTab } from "@/components/casefile/Inspector";
import { PullThread } from "@/components/casefile/PullThread";
import { FailureView } from "@/components/casefile/FailureView";
import { SourcesView } from "@/components/casefile/SourcesView";

const RAIL_KEY = "omniops-rail";
const FOLD_MS = 280;

export default function WorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = React.use(params);
  return <WorkspaceScreen key={id} workspaceId={id} />;
}

function readLocation(): { view: WorkspaceView; investigation: string | null } {
  if (typeof window === "undefined") return { view: "ask", investigation: null };
  const params = new URLSearchParams(window.location.search);
  const investigation = params.get("investigation");
  if (investigation) return { view: "investigation", investigation };
  if (params.get("view") === "sources") return { view: "sources", investigation: null };
  return { view: "ask", investigation: null };
}

function WorkspaceScreen({ workspaceId }: { workspaceId: string }) {
  const reduced = useReducedMotion();
  const { workspace, files, tables, isLoading, isError, mutateAll } = useWorkspaceData(workspaceId);
  const { outlines } = useOutlines(workspaceId, files);
  const { history, isLoading: historyLoading, mutate: mutateHistory } = useInvestigationHistory(workspaceId);
  const [location, setLocation] = useState<{ view: WorkspaceView; investigation: string | null }>({ view: "ask", investigation: null });
  const activeId = location.view === "investigation" ? location.investigation : null;
  const { state: stream, cancel } = useInvestigationStream(activeId);
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [tab, setTab] = useState<InspectorTab>("passage");
  const [submitting, setSubmitting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<SourceDocument | null>(null);
  const [previewTable, setPreviewTable] = useState<TabularDataset | null>(null);
  const [phase, setPhase] = useState<"field" | "folding" | "brief">("field");
  const [foldPlayed, setFoldPlayed] = useState(false);
  const witnessedRun = useRef(false);
  const passageRef = useRef<HTMLDivElement>(null);
  const submission = useRef(false);

  useEffect(() => {
    const sync = () => setLocation(readLocation());
    sync();
    try {
      setCollapsed(window.localStorage.getItem(RAIL_KEY) === "collapsed");
    } catch {
      /* preference only */
    }
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const navigate = useCallback((next: { view: WorkspaceView; investigation?: string | null }) => {
    const url = new URL(window.location.href);
    url.searchParams.delete("investigation");
    url.searchParams.delete("view");
    if (next.view === "investigation" && next.investigation) url.searchParams.set("investigation", next.investigation);
    if (next.view === "sources") url.searchParams.set("view", "sources");
    window.history.pushState(null, "", url.pathname + url.search);
    setLocation({ view: next.view, investigation: next.investigation ?? null });
    setSelection(null);
  }, []);

  // Reset per-investigation presentation state.
  useEffect(() => {
    witnessedRun.current = false;
    setPhase("field");
    setFoldPlayed(false);
    setSelection(null);
  }, [activeId]);

  const snapshot = deriveInvestigationStage(stream);
  const terminal = snapshot.terminal;
  const running = Boolean(activeId) && !terminal && stream.status !== "idle";
  useEffect(() => {
    if (running && stream.objective) witnessedRun.current = true;
  }, [running, stream.objective]);

  const completed = stream.status === "completed" && Boolean(stream.finalResponse);
  const generation = !activeId ? null : completed ? "completed" : snapshot.batchReceived ? "batch" : null;
  const { lineage } = useLineage(activeId, generation);

  const evidenceIndex = useMemo(() => indexLineage(lineage), [lineage]);
  const model = useMemo(
    () => (completed && stream.finalResponse && lineage ? buildBrief(stream.finalResponse, lineage) : null),
    [completed, stream.finalResponse, lineage],
  );

  // The fold plays only when this view witnessed the run reach completion.
  useEffect(() => {
    if (!model) return;
    if (!witnessedRun.current || foldPlayed) {
      setPhase("brief");
      return;
    }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setPhase("folding");
    const timer = window.setTimeout(() => {
      setPhase("brief");
      setFoldPlayed(true);
      void mutateHistory();
    }, reduced ? 150 : FOLD_MS);
    return () => window.clearTimeout(timer);
  }, [model, foldPlayed, mutateHistory]);

  useEffect(() => {
    if (terminal) void mutateHistory();
  }, [terminal, mutateHistory]);

  useEffect(() => {
    const base = workspace?.name ?? "Workspace";
    document.title = activeId && stream.objective ? `${stream.objective.slice(0, 60)} · OmniOps` : `${base} · OmniOps`;
  }, [workspace?.name, activeId, stream.objective]);

  const canEdit = workspace?.user_role ? workspace.user_role !== "viewer" : true;
  const readyCount = files.filter((file) => ["ready", "partially_ready"].includes(file.processing_status)).length;

  const start = useCallback(
    async (objective: string) => {
      if (submission.current) return false;
      submission.current = true;
      setSubmitting(true);
      setStartError(null);
      try {
        const session = await apiClient.post<InvestigationSession>(`/workspaces/${workspaceId}/investigations`, { objective, max_steps: 12 });
        setPrefill(null);
        navigate({ view: "investigation", investigation: session.id });
        void mutateHistory();
        return true;
      } catch (error) {
        setStartError(error instanceof Error ? error.message : "Investigation could not be started.");
        return false;
      } finally {
        submission.current = false;
        setSubmitting(false);
      }
    },
    [workspaceId, navigate, mutateHistory],
  );

  const returnFocus = useRef<HTMLElement | null>(null);
  const select = useCallback((next: Selection) => {
    // Remember what opened the inspector so Esc/close can hand focus back to it.
    setSelection((previous) => {
      if (!previous && document.activeElement instanceof HTMLElement && document.activeElement !== document.body) returnFocus.current = document.activeElement;
      return next;
    });
    setTab(next.kind === "trace" ? "trace" : next.kind === "source" ? "source" : next.kind === "calculation" ? "claim" : "passage");
  }, []);

  const closeInspector = useCallback(() => {
    const anchor = selection && "anchorId" in selection ? selection.anchorId : null;
    const opener = returnFocus.current;
    returnFocus.current = null;
    setSelection(null);
    window.requestAnimationFrame(() => {
      const target = opener && opener.isConnected ? opener : anchor ? document.getElementById(anchor) : null;
      target?.focus();
    });
  }, [selection]);

  const onFailureAction = (action: FailureAction) => {
    if (action === "edit") {
      setPrefill(stream.objective);
      navigate({ view: "ask" });
    } else if (action === "sources") navigate({ view: "sources" });
    else if (action === "retry") void start(stream.objective);
    else if (action === "trace") select({ kind: "trace" });
  };

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      try {
        window.localStorage.setItem(RAIL_KEY, value ? "expanded" : "collapsed");
      } catch {
        /* preference only */
      }
      return !value;
    });
  };

  const elapsed = useElapsed(stream.createdAt, running);
  const runningDetail = useStageDetail(stream);

  if (isLoading)
    return (
      <main id="main-content" className="mx-auto max-w-xl p-8">
        <LoadingState label="Loading workspace" />
      </main>
    );

  if (!workspace)
    return (
      <main id="main-content" className="mx-auto max-w-xl space-y-5 p-8">
        <Link href="/" className="btn-ghost">
          <ArrowLeft className="h-4 w-4" /> All casefiles
        </Link>
        <ErrorState title="Workspace unavailable" message="The workspace could not be loaded. Check your access or try again." onRetry={mutateAll} />
      </main>
    );

  const inspectorOpen = Boolean(selection) && location.view === "investigation";
  const breadcrumb = (tail: string) => (
    <p className="t-meta truncate text-ink-3">
      {workspace.name} <span aria-hidden="true">&nbsp;/&nbsp;</span> {tail}
    </p>
  );

  let content: React.ReactNode;
  if (location.view === "sources") {
    content = (
      <div className="page-frame mx-auto">
        <SourcesView workspace={workspace} files={files} tables={tables} outlines={outlines} canEdit={canEdit} onRefresh={mutateAll} onPreviewFile={setPreviewFile} onPreviewTable={setPreviewTable} />
      </div>
    );
  } else if (location.view === "ask" || !activeId) {
    content = (
      <div className="page-frame mx-auto">
        <EmptyWorkspace
          key={prefill ?? "empty"}
          workspace={workspace}
          files={files}
          tables={tables}
          outlines={outlines}
          submitting={submitting}
          onStart={start}
          onSourcesChanged={mutateAll}
          onManageSources={() => navigate({ view: "sources" })}
          canEdit={canEdit}
          prefill={prefill}
        />
        {startError && (
          <div className="mx-auto -mt-12 max-w-[720px]">
            <ErrorState title="Could not start investigation" message={startError} />
          </div>
        )}
      </div>
    );
  } else if (phase === "brief" && model) {
    content = (
      <div className="page-frame page-frame-wide brief-frame">
        <Brief
          model={model}
          objective={stream.objective}
          files={files}
          outlines={outlines}
          selection={selection}
          onSelect={select}
          fold={foldPlayed}
          header={<div className="mb-3">{breadcrumb(stream.objective)}</div>}
        />
      </div>
    );
  } else {
    const failed = stream.status === "failed" || stream.status === "cancelled";
    const detail = failed
      ? `${snapshot.stageKnown ? "Stopped here" : "Stopped · stage not received"}${stream.failureCode ? ` · ${stream.failureCode}` : ""}`
      : runningDetail;
    content = (
      <div className="page-frame mx-auto">
        {breadcrumb(failed ? stream.objective || "Investigation" : "Investigation")}
        <h1 className="lead mt-3 max-w-[880px] text-ink">{stream.objective || "Loading investigation…"}</h1>
        <p className="t-meta mt-2.5 text-ink-3" aria-live="off">
          {stream.createdAt ? `Started ${formatClock(stream.createdAt)}` : "Connecting to saved history"}
          {running && elapsed != null ? ` · running for ${Math.floor(elapsed / 1000)} s` : ""}
          {completed && !model ? " · completed, loading the saved brief" : ""}
          {stream.connection === "reconnecting" ? " · reconnecting, history preserved" : ""}
        </p>
        <div className="mt-3">
          <StageBar snapshot={snapshot} detail={detail} />
        </div>
        <p className="sr-only" aria-live="polite">
          {terminal === "completed" ? "Investigation complete. Opening the brief." : failed ? "Investigation stopped." : `Current stage: ${snapshot.current.label}.`}
        </p>
        {failed ? (
          <FailureView stream={stream} onAction={onFailureAction} canEdit={canEdit} />
        ) : (
          <div className="mt-[42px]">
            <InvestigationField
              stream={stream}
              files={files}
              tables={tables}
              outlines={outlines}
              evidence={evidenceIndex.passages}
              calculations={evidenceIndex.calculations}
              selection={selection}
              onSelect={select}
              onCancel={() => void cancel()}
              canCancel={canEdit}
              folding={phase === "folding"}
            />
          </div>
        )}
        {stream.errorMessage && !failed && stream.status !== "completed" && (
          <div className="mt-5">
            <ErrorState title="Runtime notice" message={stream.errorMessage} />
          </div>
        )}
      </div>
    );
  }

  const anchorId = selection && "anchorId" in selection ? selection.anchorId : null;

  return (
    <div className="app-shell" data-rail={collapsed ? "collapsed" : undefined} data-inspector={inspectorOpen ? "open" : undefined}>
      <Rail
        workspace={workspace}
        sourceCount={files.length}
        readyCount={readyCount}
        history={history?.items ?? []}
        historyLoading={historyLoading}
        activeInvestigationId={activeId}
        view={location.view}
        running={running}
        collapsed={collapsed}
        drawerOpen={drawer}
        onToggleCollapsed={toggleCollapsed}
        onCloseDrawer={() => setDrawer(false)}
        onNewInvestigation={() => navigate({ view: "ask" })}
        onOpenSources={() => navigate({ view: "sources" })}
        onOpenInvestigation={(id) => navigate({ view: "investigation", investigation: id })}
      />
      <main id="main-content" className="main-column" tabIndex={-1}>
        <MobileBar title={location.view === "investigation" && stream.objective ? stream.objective : workspace.name} onMenu={() => setDrawer(true)} />
        {isError && (
          <div className="px-10 pt-6">
            <ErrorState title="Some workspace data is unavailable" message="Source counts may be incomplete. Retry to reload the workspace." onRetry={mutateAll} />
          </div>
        )}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={`${location.view}:${activeId ?? ""}`} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? { opacity: 0 } : { opacity: 0, y: -6 }} transition={{ duration: reduced ? 0.08 : motionTokens.quick, ease: motionTokens.ease }}>
            {content}
          </motion.div>
        </AnimatePresence>
      </main>
      {inspectorOpen && selection && (
        <>
        {/* Bottom-sheet scrim (below 1024 only); tapping it closes the sheet. */}
        <div className="inspector-scrim" aria-hidden="true" onClick={closeInspector} />
        <div className="inspector-column">
          <Inspector
            selection={selection}
            tab={tab}
            onTab={setTab}
            onSelect={select}
            onClose={closeInspector}
            model={model}
            evidence={evidenceIndex.passages}
            outlines={outlines}
            files={files}
            tables={tables}
            completed={completed && Boolean(model)}
            stream={stream}
            onCancel={() => void cancel()}
            onOpenSource={setPreviewFile}
            passageRef={passageRef}
          />
        </div>
        </>
      )}
      {inspectorOpen && tab === "passage" && selection?.kind === "passage" && (
        <PullThread anchorId={anchorId} target={passageRef} version={`${selection.chunkId}:${anchorId}`} />
      )}
      <TabularPreviewModal table={previewTable} onClose={() => setPreviewTable(null)} />
      <SourcePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
    </div>
  );
}
