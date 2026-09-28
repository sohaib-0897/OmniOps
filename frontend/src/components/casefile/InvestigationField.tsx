"use client";

import { useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { motionTokens } from "@/motion/tokens";
import type { PassageMap, SourceDocument, TabularDataset } from "@/types/api";
import type { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import type { CalculationRef, PassageRef } from "@/lib/brief-model";
import type { PassageState } from "@/lib/source-track";
import { positionOfChunk } from "@/lib/source-track";
import {
  describeEvent,
  deriveInvestigationStage,
  INVESTIGATION_STAGES,
  type InvestigationStageSnapshot,
} from "@/lib/investigation-stages";
import { excerpt, passageLocatorLabel, sharedLeadLines, type Selection } from "./Brief";
import { SourceRow } from "./SourceRow";

const clock = (value: string | null | undefined) =>
  value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    : "—";

export function elapsedLabel(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Real wall-clock elapsed time since a persisted timestamp. Display only. */
function useElapsed(since: string | null, running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  if (!since || !Number.isFinite(Date.parse(since))) return null;
  return Math.max(0, now - Date.parse(since));
}

/** Sub-status under the current stage: its description plus real elapsed time. */
export function useStageDetail(stream: InvestigationStreamState): string | null {
  const snapshot = deriveInvestigationStage(stream);
  const running = !snapshot.terminal;
  const elapsed = useElapsed(stream.createdAt, running);
  // Writing starts at the persisted transition into synthesis.
  const writingSince = [...stream.timeline].reverse().find((event) => event.type === "synthesis.started" || (event.type === "state.changed" && String(event.payload?.to).toLowerCase() === "synthesizing"))?.timestamp ?? null;
  const writingElapsed = useElapsed(writingSince, running && snapshot.index === 3);
  if (snapshot.terminal) return null;
  if (snapshot.index === 3 && writingElapsed != null) return `${snapshot.detail} · ${elapsedLabel(writingElapsed)}`;
  return elapsed != null ? `${snapshot.detail} · ${elapsedLabel(elapsed)}` : snapshot.detail;
}

export function StageBar({
  snapshot,
  detail,
}: {
  snapshot: InvestigationStageSnapshot;
  detail: string | null;
}) {
  const failed = snapshot.terminal === "failed" || snapshot.terminal === "cancelled";
  // A stopped run whose stopping stage was not received marks no stage at all.
  const unknown = failed && !snapshot.stageKnown;
  const doneThrough = snapshot.terminal === "completed" ? INVESTIGATION_STAGES.length : unknown ? 0 : snapshot.index;
  const progress = Math.min(doneThrough, INVESTIGATION_STAGES.length - 1) / (INVESTIGATION_STAGES.length - 1);
  const last = INVESTIGATION_STAGES.length - 1;
  const detailIndex = Math.min(snapshot.index, last);
  const reduced = useReducedMotion();
  return (
    <div>
      <div className="stage-bar">
        <motion.span className="stage-progress" data-failed={failed || undefined} initial={false} animate={{ width: `calc((100% - 16px) * ${progress})` }} transition={{ duration: reduced ? 0 : motionTokens.panel, ease: motionTokens.ease }} aria-hidden="true" />
        <ol className="stage-list" aria-label="Investigation stages">
        {INVESTIGATION_STAGES.map((stage, index) => {
          const state = unknown
            ? "unknown"
            : snapshot.terminal === "completed" || index < snapshot.index
              ? "done"
              : index === snapshot.index
                ? failed
                  ? "failed"
                  : "current"
                : "upcoming";
          return (
            <li key={stage.id} className="stage" data-state={state} data-stage-id={stage.id} aria-current={state === "current" ? "step" : undefined} style={{ ["--i" as string]: index }}>
              <span className="stage-node" aria-hidden="true">{state === "done" && <Check className="h-2.5 w-2.5" strokeWidth={3} />}</span>
              <span className="stage-label">
                {stage.label}
                <span className="sr-only">{state === "done" ? ", done" : state === "current" ? ", in progress" : state === "failed" ? ", stopped here" : state === "unknown" ? ", stage not received" : ", not started"}</span>
              </span>
            </li>
          );
        })}
        </ol>
      </div>
      {/* Sub-status sits under the current node (Figma B04/B05): real stage description and elapsed time. */}
      {detail && (snapshot.terminal == null || failed) && (
        <p className="stage-detail" data-edge={detailIndex === 0 ? "start" : detailIndex === last ? "end" : undefined} style={{ ["--i" as string]: detailIndex }}>
          {detail}
        </p>
      )}
    </div>
  );
}

export interface FieldProps {
  stream: InvestigationStreamState;
  files: SourceDocument[];
  tables: TabularDataset[];
  outlines: Record<string, PassageMap>;
  evidence: Map<string, PassageRef>;
  calculations: Map<string, CalculationRef>;
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
  onCancel?: () => void;
  canCancel: boolean;
  folding: boolean;
}

export function InvestigationField({
  stream,
  files,
  tables,
  outlines,
  evidence,
  calculations,
  selection,
  onSelect,
  onCancel,
  canCancel,
  folding,
}: FieldProps) {
  const snapshot = deriveInvestigationStage(stream);
  const reduced = useReducedMotion();
  const running = !snapshot.terminal;
  const [showAll, setShowAll] = useState(false);
  const batch = snapshot.batchReceived;

  const states = useMemo(() => {
    const map = new Map<string, PassageState>();
    evidence.forEach((_, id) => map.set(id, "evidence"));
    return map;
  }, [evidence]);

  const perSource = useMemo(() => {
    const counts = new Map<string, number>();
    evidence.forEach((passage) => passage.sourceId && counts.set(passage.sourceId, (counts.get(passage.sourceId) ?? 0) + 1));
    return counts;
  }, [evidence]);

  const sqlCalcs = [...calculations.values()].filter((calc) => calc.type === "sql_query").length;
  const allCalcs = calculations.size;
  const spreadsheetCount = files.filter((file) => file.modality === "spreadsheet").length;
  const indexedTotal = files.reduce((sum, file) => sum + (outlines[file.id]?.passage_count ?? 0), 0);
  const cards = [...evidence.values()].sort((a, b) => {
    const fa = files.findIndex((file) => file.id === a.sourceId);
    const fb = files.findIndex((file) => file.id === b.sourceId);
    if (fa !== fb) return fa - fb;
    return (a.chunkIndex ?? 0) - (b.chunkIndex ?? 0);
  });
  const visibleCards = showAll ? cards : cards.slice(0, 6);
  const headers = useMemo(() => sharedLeadLines([...evidence.values()].map((passage) => passage.content)), [evidence]);
  const savedEvents = stream.timeline.filter((event) => event.timestamp);
  const shownEvents = savedEvents.slice(-7);

  return (
    <div className={folding ? "fold-away" : undefined}>
      <section className="field-panel" aria-label="Investigation field">
        <div className="field-main">
          <h2 className="t-overline mb-2">Sources</h2>
          <div className="flex flex-col gap-1.5">
            {files.map((file) => {
              const map = outlines[file.id];
              const count = perSource.get(file.id) ?? 0;
              const fileTables = tables.filter((table) => table.source_id === file.id);
              const right =
                file.modality === "spreadsheet"
                  ? batch && sqlCalcs
                    ? // SQL runs against all workspace tables; attribute it to a file only when there is one.
                      spreadsheetCount === 1
                      ? `${sqlCalcs} SQL ${sqlCalcs === 1 ? "calculation" : "calculations"} · query recorded`
                      : `${sqlCalcs} SQL ${sqlCalcs === 1 ? "calculation" : "calculations"} across workspace tables`
                    : `${fileTables.length} ${fileTables.length === 1 ? "table" : "tables"} · queried with SQL, not passage-indexed`
                  : batch && map
                    ? `${count} of ${map.passage_count} passages retrieved as evidence`
                    : map
                      ? `${map.passage_count} passages indexed`
                      : undefined;
              return (
                <SourceRow
                  key={file.id}
                  file={file}
                  map={map}
                  tables={fileTables}
                  states={states}
                  focusChunkId={selection?.kind === "passage" ? selection.chunkId : null}
                  right={right}
                  ticks
                  grow={batch}
                  showIcon
                  height={10}
                  labelGap={4}
                  padded={false}
                  onSelectPassage={(chunkId) => evidence.has(chunkId) && onSelect({ kind: "passage", chunkId })}
                />
              );
            })}
          </div>

          <h2 className="t-overline mb-2.5 mt-[18px]">{batch ? `Evidence · ${evidence.size} ${evidence.size === 1 ? "passage" : "passages"}` : "Evidence"}</h2>
          {!batch ? (
            <div className="evidence-empty">
              <p>Evidence appears here when the search phase is saved. OmniOps saves planning and search together, so passages arrive at once rather than one by one.</p>
            </div>
          ) : evidence.size === 0 ? (
            <div className="evidence-empty">
              <p>{allCalcs ? "The search phase saved calculations but no document passages." : "The search phase was saved without any evidence passages."}</p>
            </div>
          ) : (
            <>
              <ul className="evidence-grid">
                {visibleCards.map((passage, index) => {
                  const map = passage.sourceId ? outlines[passage.sourceId] : undefined;
                  const active = selection?.kind === "passage" && selection.chunkId === passage.chunkId;
                  return (
                    <li key={passage.chunkId}>
                      <motion.button
                        type="button"
                        className="evidence-card"
                        initial={reduced ? false : { opacity: 0, y: -8, scale: 0.985 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ duration: reduced ? 0 : motionTokens.panel, delay: reduced ? 0 : Math.min(index * motionTokens.stagger, 0.33), ease: motionTokens.ease }}
                        whileHover={reduced ? undefined : { y: -2 }}
                        whileTap={reduced ? undefined : { scale: 0.995 }}
                        data-active={active || undefined}
                        aria-label={`${passage.sourceName}, ${passageLocatorLabel(passage, map)}. Retrieved as evidence. Open passage.`}
                        onClick={() => onSelect({ kind: "passage", chunkId: passage.chunkId })}
                      >
                        <span className="mb-1 flex items-center justify-between gap-2">
                          <span className="mono text-ink-3">{passageLocatorLabel(passage, map).replace(/ · /g, "  ·  ")}</span>
                          <span className="t-meta text-ink-2">Evidence</span>
                        </span>
                        <span className="quote">{excerpt(passage.content, 110, headers)}</span>
                      </motion.button>
                    </li>
                  );
                })}
              </ul>
              {cards.length > 6 && (
                <button type="button" className="t-meta mt-3 text-ink-2 hover:text-ink" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? "Show fewer" : `+ ${cards.length - 6} more evidence ${cards.length - 6 === 1 ? "passage" : "passages"}`}
                </button>
              )}
            </>
          )}
        </div>

        <aside className="field-ledger" aria-label="Ledger">
          <h2 className="t-overline">Ledger</h2>
          <dl>
            {[
              { value: indexedTotal || null, label: "Passages indexed" },
              { value: batch ? evidence.size : null, label: "Evidence passages" },
              { value: batch ? sqlCalcs : null, label: sqlCalcs === 1 ? "SQL calculation" : "SQL calculations" },
              { value: null, label: "Claims with verified citations" },
            ].map((row) => (
              <div key={row.label} className="ledger-row">
                <dd className="ledger-value" data-empty={row.value == null || undefined}>{row.value == null ? "—" : row.value.toLocaleString("en-US")}</dd>
                <dt className="ledger-label">{row.label}</dt>
              </div>
            ))}
          </dl>
          <div className="mt-[19px] border-t border-line pt-4">
            <h2 className="t-overline">Saved events</h2>
            <ol aria-live="polite">
              {savedEvents.length > shownEvents.length && <li className="t-meta pb-1 text-ink-3">{savedEvents.length - shownEvents.length} earlier events in the trace</li>}
              {shownEvents.map((event, index) => {
                const { label, detail: eventDetail } = describeEvent(event);
                const last = index === shownEvents.length - 1 && batch && running;
                return (
                  <li key={event.id} className="event-row" data-live={last || undefined}>
                    <time dateTime={event.timestamp}>{clock(event.timestamp)}</time>
                    <span>{label}{eventDetail ? <span className="text-ink-2"> · {eventDetail}</span> : null}</span>
                  </li>
                );
              })}
              {running && !batch && (
                <li className="event-row" data-live="true">
                  <time>—</time>
                  <span>Planning and search in progress. Their events are saved together when this phase ends.</span>
                </li>
              )}
            </ol>
          </div>
        </aside>
      </section>

      {running && (
        <div className="mt-[26px] flex flex-wrap items-center gap-4">
          {canCancel && onCancel && (
            <button type="button" className="btn-outline h-[34px]" onClick={onCancel}>
              Stop investigation
            </button>
          )}
          <p className="t-meta text-ink-2">You can leave this page. The run continues and the history keeps its place.</p>
        </div>
      )}
    </div>
  );
}

export function stageHeaderLine(stream: InvestigationStreamState, elapsed: number | null) {
  return `Started ${clock(stream.createdAt)}${elapsed != null ? ` · running for ${Math.floor(elapsed / 1000)} s` : ""}`;
}

export { clock as formatClock, useElapsed, positionOfChunk };
