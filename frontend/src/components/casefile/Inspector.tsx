"use client";

import { useEffect, useMemo, useRef, type ReactNode, type RefObject } from "react";
import { Check, ChevronLeft, ChevronRight, Minus, X } from "lucide-react";
import type { PassageMap, SourceDocument, TabularDataset } from "@/types/api";
import type { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import type { BriefClaim, BriefModel, CalculationRef, PassageRef } from "@/lib/brief-model";
import { explainReason, sharedFigures } from "@/lib/brief-model";
import type { PassageState } from "@/lib/source-track";
import { positionOfChunk } from "@/lib/source-track";
import { LiveActivityStepper } from "@/components/workspace/LiveActivityStepper";
import { SourceTrack } from "./SourceTrack";
import { passageLocatorLabel, type Selection } from "./Brief";
import { sourceMeta } from "./SourceRow";

export type InspectorTab = "passage" | "claim" | "source" | "trace";

const TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: "passage", label: "Passage" },
  { id: "claim", label: "Claim" },
  { id: "source", label: "Source" },
  { id: "trace", label: "Trace" },
];

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Underline figures shared with the claim. Neutral styling: a text match only. */
function markFigures(content: string, figures: string[]): ReactNode {
  if (!figures.length) return content;
  const pattern = new RegExp(`(${figures.map(escapeRegExp).join("|")})`, "g");
  return content.split(pattern).map((part, index) => (figures.includes(part) ? <mark key={index}>{part}</mark> : part));
}

function CitationSeal({ claim, completed }: { claim: BriefClaim | null; completed: boolean }) {
  if (!claim || !completed) {
    return (
      <div className="seal" data-status="neutral">
        <span className="seal-mark"><Minus className="h-4 w-4" aria-hidden="true" /></span>
        <div>
          <p className="seal-title">Retrieved as evidence</p>
          <p className="t-meta mt-1 text-ink-2">
            {completed
              ? "No claim with verified citations cites this passage. It stays neutral."
              : "No claim has been written or checked yet. Evidence stays neutral until the brief is saved."}
          </p>
        </div>
      </div>
    );
  }
  if (claim.status === "VERIFIED") {
    return (
      <div className="seal" data-status="verified">
        <span className="seal-mark"><Check className="h-5 w-5" aria-hidden="true" /></span>
        <div>
          <p className="seal-title">Citation verified</p>
          <p className="t-meta mt-1 text-ink-2">
            This claim was saved as VERIFIED: each citation resolves to this investigation and workspace, and its quote matches the source exactly. This checks the citation chain, not the conclusion.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="seal" data-status="rejected">
      <span className="seal-mark"><X className="h-4 w-4" aria-hidden="true" /></span>
      <div>
        <p className="seal-title">{claim.status === "REJECTED" ? "Rejected" : "Verification not reported"}</p>
        <ul className="t-meta mt-1 text-ink-2">
          {claim.errors.length ? claim.errors.map((error) => <li key={error}>{explainReason(error)}</li>) : <li>No citation check was recorded for this claim.</li>}
        </ul>
      </div>
    </div>
  );
}

function Lineage({ cited }: { cited: boolean }) {
  return (
    <div className="lineage" data-cited={cited} aria-label={cited ? "Lineage: source, passage, evidence, claim" : "Lineage: source, passage, evidence"}>
      <span>Source</span>
      <span>Passage</span>
      <span>Evidence</span>
      <span style={cited ? undefined : { opacity: 0.5 }}>Claim</span>
    </div>
  );
}

function CalculationPanel({ calculation, number }: { calculation: CalculationRef; number: number | null }) {
  const output = JSON.stringify(calculation.output, null, 2);
  return (
    <section aria-label="Calculation" className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="calc-marker">ƒ{number ?? "?"}</span>
        <span className="t-label text-ink">{calculation.type === "sql_query" ? "SQL calculation" : "Calculation"}</span>
      </div>
      <p className="t-meta text-ink-3">
        Calculations are not passage citations, so no thread is drawn. The query and its saved output are shown exactly as recorded.
      </p>
      <div>
        <p className="t-overline mb-2">Query</p>
        <pre className="mono overflow-x-auto whitespace-pre-wrap rounded-control border border-line bg-canvas p-3 text-ink-2">{calculation.code || "Not recorded"}</pre>
      </div>
      <div>
        <p className="t-overline mb-2">Saved output</p>
        <pre className="mono max-h-64 overflow-auto whitespace-pre-wrap rounded-control border border-line bg-canvas p-3 text-ink-2">{output ? (output.length > 6000 ? `${output.slice(0, 6000)}\n…` : output) : "Not recorded"}</pre>
      </div>
      <p className="t-meta text-ink-3">Reproducibility hash <span className="mono text-ink-2">{calculation.hash ?? "not recorded"}</span></p>
    </section>
  );
}

export interface InspectorProps {
  selection: Selection;
  tab: InspectorTab;
  onTab: (tab: InspectorTab) => void;
  onSelect: (selection: Selection) => void;
  onClose: () => void;
  model: BriefModel | null;
  /** Passages known before completion (neutral evidence), keyed by chunk id. */
  evidence: Map<string, PassageRef>;
  outlines: Record<string, PassageMap>;
  files: SourceDocument[];
  tables: TabularDataset[];
  completed: boolean;
  stream: InvestigationStreamState;
  onCancel: () => void;
  onOpenSource: (file: SourceDocument) => void;
  passageRef: RefObject<HTMLDivElement>;
}

export function Inspector({
  selection,
  tab,
  onTab,
  onSelect,
  onClose,
  model,
  evidence,
  outlines,
  files,
  tables,
  completed,
  stream,
  onCancel,
  onOpenSource,
  passageRef,
}: InspectorProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  const passages = model?.passages ?? evidence;
  const chunkId = selection.kind === "passage" ? selection.chunkId : null;
  const passage = chunkId ? passages.get(chunkId) ?? null : null;
  const claim: BriefClaim | null = useMemo(() => {
    if (!model) return null;
    const claimId = "claimId" in selection ? selection.claimId : null;
    if (claimId) return model.claims.find((item) => item.claimId === claimId) ?? null;
    if (chunkId) return model.claims.find((item) => item.status === "VERIFIED" && item.citations.some((citation) => citation.chunkId === chunkId)) ?? null;
    return null;
  }, [model, selection, chunkId]);
  const calculation = selection.kind === "calculation" ? model?.calculations.get(selection.calcId) ?? null : null;
  const sourceId = selection.kind === "source" ? selection.sourceId : passage?.sourceId ?? null;
  const file = sourceId ? files.find((item) => item.id === sourceId) ?? null : null;
  const map = sourceId ? outlines[sourceId] : undefined;
  const citedNumber = chunkId && model ? model.citationNumbers.get(chunkId) ?? null : null;
  const total = model?.citationOrder.length ?? 0;
  const cited = Boolean(completed && citedNumber != null);

  const states = useMemo(() => {
    const result = new Map<string, PassageState>();
    passages.forEach((_, id) => result.set(id, "evidence"));
    if (completed && model) model.citedChunkIds.forEach((id) => result.set(id, "cited"));
    return result;
  }, [passages, completed, model]);

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [selection, tab]);

  const step = (delta: number) => {
    if (!model || !total) return;
    const current = citedNumber ?? 0;
    const next = ((current - 1 + delta + total) % total) + 1;
    onSelect({ kind: "passage", chunkId: model.citationOrder[next - 1] });
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) return;
      if (event.key === "Escape") onClose();
      else if (event.key === "]") step(1);
      else if (event.key === "[") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const figures = passage && claim && completed && claim.status === "VERIFIED" ? sharedFigures(claim.statement, passage.content) : [];
  const position = passage && map ? positionOfChunk(map, passage.chunkId) : -1;
  const sharedBy = chunkId ? model?.citedBy.get(chunkId) ?? [] : [];

  let body: ReactNode;
  if (tab === "trace") {
    body = <LiveActivityStepper streamState={stream} onCancel={onCancel} />;
  } else if (tab === "source") {
    body = file ? (
      <div className="flex flex-col gap-4">
        <div>
          <p className="t-label text-ink">{file.file_name}</p>
          <p className="t-meta text-ink-3">{sourceMeta(file, map, tables.filter((table) => table.source_id === file.id))}</p>
        </div>
        {map && map.passage_count > 0 && (
          <SourceTrack map={map} label={file.file_name} states={states} focusChunkId={chunkId} citedBy={model?.citedBy} height={10} ticks initialWidth={340} onSelectPassage={(id) => onSelect({ kind: "passage", chunkId: id })} />
        )}
        <p className="t-meta text-ink-3">Grey segments are indexed passages; darker ones were retrieved as evidence; sea-glass ones are cited by claims with verified citations.</p>
        <button type="button" className="btn-outline self-start" onClick={() => onOpenSource(file)}>Open source text</button>
      </div>
    ) : (
      <p className="t-body text-ink-2">Select a passage or citation to see its source. If the source was deleted, its passages are no longer available.</p>
    );
  } else if (calculation && (tab === "claim" || tab === "passage")) {
    body = (
      <div className="flex flex-col gap-6">
        {claim && <p className="r-body text-ink">{claim.statement}</p>}
        <CalculationPanel calculation={calculation} number={model?.calcOrder.indexOf(calculation.id) != null ? model!.calcOrder.indexOf(calculation.id) + 1 : null} />
      </div>
    );
  } else if (tab === "claim") {
    body = claim ? (
      <div className="flex flex-col gap-5">
        <p className="r-body text-ink">{claim.statement}</p>
        <CitationSeal claim={claim} completed={completed} />
        {claim.citations.length > 0 && (
          <div>
            <p className="t-overline mb-2">Cites</p>
            <ul className="flex flex-col gap-1">
              {claim.citations.map((citation) => {
                const item = passages.get(citation.chunkId);
                const itemMap = item?.sourceId ? outlines[item.sourceId] : undefined;
                return (
                  <li key={citation.number}>
                    <button type="button" className="rail-item h-auto py-2" aria-current={citation.chunkId === chunkId ? "true" : undefined} onClick={() => onSelect({ kind: "passage", chunkId: citation.chunkId, claimId: claim.claimId })}>
                      <span className="cite" aria-hidden="true">{citation.number}</span>
                      <span className="rail-item-label">{item ? `${item.sourceName} · ${passageLocatorLabel(item, itemMap)}` : "Passage unavailable"}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {claim.unresolved.length > 0 && <p className="t-meta text-ink-3">{claim.unresolved.length} cited passage{claim.unresolved.length === 1 ? " is" : "s are"} unavailable; the source may have been deleted.</p>}
        {claim.calculations.map(({ number, calculation: calc }) => (
          <CalculationPanel key={calc.id} calculation={calc} number={number} />
        ))}
      </div>
    ) : (
      <p className="t-body text-ink-2">{completed ? "No claim with verified citations cites this passage." : "Claims are written and checked after the search phase. None exist yet."}</p>
    );
  } else {
    body = passage ? (
      <div className="flex flex-col gap-6">
        <div>
          <p className="t-label text-ink">{passage.sourceName}</p>
          <p className="t-meta text-ink-3">
            {[position >= 0 && map?.page_number[position] != null ? `Page ${map.page_number[position]}` : passage.pageNumber != null ? `Page ${passage.pageNumber}` : null,
              position >= 0 && map ? `passage ${position + 1} of ${map.passage_count}` : null,
              "the full passage is the evidence quote"].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div ref={passageRef} className="passage-block" data-cited={cited}>
          {markFigures(passage.content, figures)}
        </div>
        <CitationSeal claim={cited ? claim : null} completed={completed} />
        {sharedBy.length > 1 && <p className="t-meta text-ink-2">Cited by claims {sharedBy.join(", ")}</p>}
        {figures.length > 0 && (
          <div>
            <p className="t-meta mb-2 text-ink-3">Also appears in this passage · text match, not verification</p>
            <div className="flex flex-wrap gap-2">
              {figures.map((figure, index) => (
                <span key={figure} className="figure-chip" style={{ animationDelay: `${index * 60}ms` }}>{figure}</span>
              ))}
            </div>
          </div>
        )}
        <div>
          <p className="t-overline mb-3">Lineage</p>
          <Lineage cited={cited} />
        </div>
        <button type="button" className="t-label self-start text-ink hover:underline" onClick={() => onTab("trace")}>
          Open full trace →
        </button>
      </div>
    ) : (
      <p className="t-body text-ink-2">Passage unavailable. Its source may have been deleted after this investigation ran.</p>
    );
  }

  const title = tab === "passage" ? "Passage" : tab === "claim" ? "Claim" : tab === "source" ? "Source" : "Trace";
  const showSpine = tab === "passage" && map && map.passage_count > 0 && !calculation;

  return (
    <aside className="inspector" aria-label="Evidence inspector">
      <div className="sheet-handle" aria-hidden="true" />
      <div className="inspector-tabs">
        <div role="tablist" aria-label="Inspector views" className="flex items-center gap-[22px]">
          {TABS.map((item) => (
            <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className="inspector-tab" onClick={() => onTab(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        {total > 0 && citedNumber != null && (
          <span className="ml-1 flex items-center gap-1 sm:ml-2">
            <button type="button" className="btn-icon h-7 w-7" aria-label="Previous citation ([)" onClick={() => step(-1)}><ChevronLeft className="h-4 w-4" /></button>
            <span className="t-meta whitespace-nowrap text-ink-3" aria-live="polite">{citedNumber} / {total}</span>
            <button type="button" className="btn-icon h-7 w-7" aria-label="Next citation (])" onClick={() => step(1)}><ChevronRight className="h-4 w-4" /></button>
          </span>
        )}
        <button type="button" className="btn-icon ml-1" aria-label="Close inspector (Esc)" onClick={onClose}><X className="h-4 w-4" /></button>
      </div>
      <div className="inspector-body" role="tabpanel" aria-label={title} data-spine={showSpine ? "true" : undefined}>
        <h2 ref={heading} tabIndex={-1} className="sr-only">{title}{passage && tab === "passage" ? `: ${passage.sourceName}` : ""}</h2>
        {showSpine ? (
          <div className="spine" style={{ height: "min(780px, calc(100dvh - 140px))" }}>
            <SourceTrack map={map!} label={`${passage?.sourceName ?? "Source"} passages`} states={states} focusChunkId={chunkId} citedBy={model?.citedBy} orientation="vertical" height={6} minSegment={3} gap={2} initialWidth={600} onSelectPassage={(id) => onSelect({ kind: "passage", chunkId: id })} />
          </div>
        ) : null}
        <div className="min-w-0">{body}</div>
      </div>
    </aside>
  );
}
