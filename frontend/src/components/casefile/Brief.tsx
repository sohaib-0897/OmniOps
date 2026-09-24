"use client";

import {
  Fragment,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { Check, Minus } from "lucide-react";
import type { PassageMap, SourceDocument } from "@/types/api";
import type { BriefClaim, BriefModel, PassageRef } from "@/lib/brief-model";
import { explainReason } from "@/lib/brief-model";
import type { PassageState } from "@/lib/source-track";
import { passageLocator, positionOfChunk } from "@/lib/source-track";
import { SourceTrack } from "./SourceTrack";
import { EvidenceChart } from "./EvidenceChart";

export type Selection =
  | { kind: "passage"; chunkId: string; claimId?: string | null; anchorId?: string }
  | { kind: "calculation"; calcId: string; claimId?: string | null; anchorId?: string }
  | { kind: "trace" }
  | { kind: "source"; sourceId: string };

const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

export function passageNumberLabel(passage: PassageRef, map: PassageMap | undefined) {
  const position = map ? positionOfChunk(map, passage.chunkId) : -1;
  const index = position >= 0 ? position + 1 : passage.chunkIndex != null ? passage.chunkIndex + 1 : null;
  return index != null ? `passage ${index}` : "passage";
}

export function passageLocatorLabel(passage: PassageRef, map: PassageMap | undefined) {
  const position = map ? positionOfChunk(map, passage.chunkId) : -1;
  const locator = position >= 0 && map ? passageLocator(map, position) : passage.pageNumber != null ? `p.${passage.pageNumber}` : null;
  return [locator, passageNumberLabel(passage, map)].filter(Boolean).join(" · ");
}

export const shortName = (name: string) => name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

/** First lines repeated across passages (running page headers). Display only; the inspector shows full text. */
export function sharedLeadLines(contents: Iterable<string>): Set<string> {
  const counts = new Map<string, number>();
  for (const content of contents) {
    const first = content.split("\n", 1)[0].trim();
    if (first.length >= 12) counts.set(first, (counts.get(first) ?? 0) + 1);
  }
  return new Set([...counts].filter(([, count]) => count > 1).map(([line]) => line));
}

export function excerpt(content: string, length = 90, skipLines?: ReadonlySet<string>) {
  const lines = content.split("\n");
  // Skip a repeated running header and a bare page label so the excerpt shows the passage itself.
  while (lines.length > 1 && (skipLines?.has(lines[0].trim()) || /^\s*page \d+\s*$/i.test(lines[0]))) lines.shift();
  const text = lines.join("\n").replace(/^#+\s.*\n/, "").replace(/\s+/g, " ").trim();
  return text.length > length ? `“${text.slice(0, length).trimEnd()}…”` : `“${text}”`;
}

/** Cited-only state map for one passage: sidenote locators highlight a single passage. */
function singleCited(chunkId: string): ReadonlyMap<string, PassageState> {
  return new Map([[chunkId, "cited" as const]]);
}

export function Markers({
  claim,
  selection,
  onSelect,
}: {
  claim: BriefClaim;
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
}) {
  if (claim.status !== "VERIFIED") return null;
  return (
    <>
      {claim.citations.map(({ number, chunkId }) => {
        const anchorId = `cite-${claim.claimId}-${number}`;
        const pressed = selection?.kind === "passage" && selection.chunkId === chunkId && selection.anchorId === anchorId;
        return (
          <button
            key={`c${number}`}
            id={anchorId}
            type="button"
            className="cite"
            aria-pressed={pressed}
            aria-label={`Citation ${number}: open the cited passage`}
            onClick={() => onSelect({ kind: "passage", chunkId, claimId: claim.claimId, anchorId })}
          >
            {number}
          </button>
        );
      })}
      {claim.calculations.map(({ number, calculation }) => {
        const anchorId = `calc-${claim.claimId}-${number}`;
        return (
          <button
            key={`f${number}`}
            id={anchorId}
            type="button"
            className="cite"
            data-kind="calc"
            aria-pressed={selection?.kind === "calculation" && selection.anchorId === anchorId}
            aria-label={`Calculation ${number}: open the query and output`}
            onClick={() => onSelect({ kind: "calculation", calcId: calculation.id, claimId: claim.claimId, anchorId })}
          >
            ƒ{number}
          </button>
        );
      })}
    </>
  );
}

function Receipt({
  model,
  outlines,
  files,
  stamp,
  onTrace,
}: {
  model: BriefModel;
  outlines: Record<string, PassageMap>;
  files: SourceDocument[];
  stamp: boolean;
  onTrace: () => void;
}) {
  const cited = model.citedChunkIds.size;
  const calcs = model.calcOrder.length;
  const states = useMemo(() => {
    const map = new Map<string, PassageState>();
    model.citedChunkIds.forEach((id) => map.set(id, "cited"));
    return map;
  }, [model]);
  const trackSources = files.filter((file) => model.sourceIds.has(file.id) && outlines[file.id]).slice(0, 3);
  const sourceCount = model.sourceIds.size;
  const grounded = cited > 0 || calcs > 0;
  const spoken = `${grounded ? "Grounded" : "Not grounded"} in ${plural(cited, "cited passage")} from ${plural(sourceCount, "source")}${calcs ? ` and ${plural(calcs, "calculation")}` : ""}. ${plural(model.verifiedClaimCount, "claim")} with verified citations. ${model.rejectedCount} rejected.`;
  return (
    <section className={`receipt ${stamp ? "receipt-stamp" : ""}`} aria-label="Provenance receipt">
      <p className="sr-only">{spoken}</p>
      <span className="receipt-seal" aria-hidden="true">
        {grounded ? <Check className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
        <span className="max-md:hidden">{grounded ? "Grounded" : "Not grounded"}</span>
      </span>
      {trackSources.length > 0 && (
        <span className="receipt-track ml-[5px] flex w-[150px] shrink-0 gap-1.5 max-md:hidden" aria-hidden="true">
          {trackSources.map((file) => (
            <span key={file.id} className="min-w-0 flex-1">
              <SourceTrack map={outlines[file.id]} label={file.file_name} states={states} height={6} minSegment={1} gap={1} initialWidth={150 / trackSources.length} decorative />
            </span>
          ))}
        </span>
      )}
      <span className="receipt-counts" aria-hidden="true">
        {plural(cited, "cited passage")}
        {calcs > 0 && ` · ${plural(calcs, "calculation")}`}
        <span className="sep">|</span>
        {plural(model.verifiedClaimCount, "claim")} with verified citations
        <span className="sep">|</span>
        {model.rejectedCount} rejected
      </span>
      <button type="button" className="receipt-link" onClick={onTrace}>
        Trace
      </button>
    </section>
  );
}

interface SidenoteItem {
  number: number;
  chunkId: string;
  anchorKey: string;
}

function Sidenotes({
  items,
  model,
  outlines,
  gridRef,
  selection,
  onSelect,
  animate,
}: {
  items: SidenoteItem[];
  model: BriefModel;
  outlines: Record<string, PassageMap>;
  gridRef: RefObject<HTMLDivElement>;
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
  animate: boolean;
}) {
  const [layout, setLayout] = useState<Array<{ tab: number; top: number }>>([]);
  const container = useRef<HTMLDivElement>(null);
  const signature = items.map((item) => `${item.number}:${item.anchorKey}`).join("|");
  const headers = useMemo(() => sharedLeadLines([...model.passages.values()].map((passage) => passage.content)), [model]);
  useLayoutEffect(() => {
    const margin = container.current;
    // The ancestor's ref is attached after this child's layout effect runs, so resolve it from the DOM too.
    const grid = gridRef.current ?? margin?.closest<HTMLElement>(".brief-grid") ?? null;
    if (!grid || !margin) return;
    const measure = () => {
      const base = margin.getBoundingClientRect().top;
      let floor = -Infinity;
      const next = items.map((item) => {
        const anchor = grid.querySelector<HTMLElement>(`[data-anchor="${item.anchorKey}"]`);
        // Figma: the tab sits 4px below the first text line (the anchor has 7px padding).
        const tab = anchor ? anchor.getBoundingClientRect().top - base + 11 : 0;
        const top = Math.max(tab - 2, floor);
        floor = top + 96;
        return { tab, top };
      });
      setLayout((previous) =>
        previous.length === next.length && previous.every((entry, index) => Math.abs(entry.tab - next[index].tab) < 0.5 && Math.abs(entry.top - next[index].top) < 0.5)
          ? previous
          : next,
      );
    };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(grid);
    window.addEventListener("resize", measure);
    // Entrance animations move anchors without resizing the grid; re-measure when they settle.
    grid.addEventListener("animationend", measure);
    void document.fonts?.ready.then(measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      grid.removeEventListener("animationend", measure);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, gridRef]);

  const height = layout.length ? Math.max(...layout.map((entry) => entry.top)) + 96 : 0;
  return (
    <div ref={container} className="relative" style={{ height }} aria-label="Evidence margin">
      {items.map((item, index) => {
        const passage = model.passages.get(item.chunkId);
        const place = layout[index];
        if (!passage || !place) return null;
        const map = passage.sourceId ? outlines[passage.sourceId] : undefined;
        const active = selection?.kind === "passage" && selection.chunkId === item.chunkId;
        const dy = place.top + 9 - (place.tab + 9);
        const style: CSSProperties = { top: place.top, animationDelay: animate ? `${280 + index * 70}ms` : undefined };
        return (
          <Fragment key={item.number}>
            <span className="margin-tab" style={{ top: place.tab }} aria-hidden="true" />
            <svg className="pointer-events-none absolute overflow-visible" style={{ left: -41, top: place.tab + 9, width: 41, height: 1 }} aria-hidden="true">
              <path d={`M0 0 C 20 0, 20 ${dy}, 41 ${dy}`} fill="none" stroke="var(--provenance)" strokeWidth="1" className={animate ? "fold-section" : undefined} />
            </svg>
            <button
              type="button"
              className={`sidenote ${animate ? "fold-section" : ""}`}
              style={style}
              data-active={active || undefined}
              aria-label={`Citation ${item.number}: ${passage.sourceName}, ${passageLocatorLabel(passage, map)}. Open the passage.`}
              onClick={() => onSelect({ kind: "passage", chunkId: item.chunkId, anchorId: undefined })}
            >
              <span className="cite" aria-hidden="true" style={{ margin: 0 }}>{item.number}</span>
              <span className="locator">{shortName(passage.sourceName)} · {passageLocatorLabel(passage, map)}</span>
              {map && (
                <span className="sidenote-track">
                  <SourceTrack map={map} label={passage.sourceName} states={singleCited(item.chunkId)} height={4} minSegment={1} initialWidth={274} decorative />
                </span>
              )}
              <span className="excerpt">{excerpt(passage.content, 90, headers)}</span>
            </button>
          </Fragment>
        );
      })}
    </div>
  );
}

export interface BriefProps {
  model: BriefModel;
  objective: string;
  files: SourceDocument[];
  outlines: Record<string, PassageMap>;
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
  /** True only when this view witnessed investigation.completed: plays the fold. */
  fold: boolean;
  header?: ReactNode;
}

export function Brief({ model, objective, files, outlines, selection, onSelect, fold, header }: BriefProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  let section = 0;
  const delay = (): CSSProperties | undefined => (fold ? { animationDelay: `${280 + section++ * 70}ms` } : undefined);
  const sectionClass = fold ? "fold-section" : "";

  // One sidenote per citation number, anchored where it is first cited.
  const sidenotes: SidenoteItem[] = [];
  const seen = new Set<number>();
  const collect = (claim: BriefClaim | null, anchorKey: string) => {
    if (!claim || claim.status !== "VERIFIED") return;
    for (const citation of claim.citations) {
      if (seen.has(citation.number)) continue;
      seen.add(citation.number);
      sidenotes.push({ number: citation.number, chunkId: citation.chunkId, anchorKey });
    }
  };
  model.findings.forEach((finding, index) => collect(finding.claim, `f${index}`));
  model.otherClaims.forEach((claim, index) => collect(claim, `o${index}`));

  const activeClaim = selection && "claimId" in selection ? selection.claimId : null;
  const chartsByClaim = new Map<string, typeof model.charts>();
  model.charts.forEach((chart) => chartsByClaim.set(chart.claimId, [...(chartsByClaim.get(chart.claimId) ?? []), chart]));
  const renderedCharts = new Set<string>();
  const chartsFor = (claim: BriefClaim | null) => {
    if (!claim) return null;
    const charts = (chartsByClaim.get(claim.claimId) ?? []).filter((chart) => !renderedCharts.has(chart.calculation.id));
    charts.forEach((chart) => renderedCharts.add(chart.calculation.id));
    return charts.map((chart) => (
      <div key={chart.calculation.id} className="my-3">
        <EvidenceChart chart={chart} onInspect={() => onSelect({ kind: "calculation", calcId: chart.calculation.id, claimId: chart.claimId })} />
      </div>
    ));
  };

  const uncitedEvidence = [...model.evidenceChunkIds].filter((id) => !model.citedChunkIds.has(id)).length;
  const rejectedClaims = model.unsupported.filter((item) => item.kind === "claim").length;

  return (
    <article className="brief" aria-label="Investigation brief">
      {header}
      <div className={fold ? "fold-in" : ""}>
        <Receipt model={model} outlines={outlines} files={files} stamp={fold} onTrace={() => onSelect({ kind: "trace" })} />
      </div>
      <div ref={gridRef} className="brief-grid mt-3">
        <div className="brief-col">
          <p className="t-body text-ink-3">{objective}</p>
          <p className="summary-label mt-1"><strong>SUMMARY</strong> · uncited; the claims below carry the citations</p>
          <p className={`lead mt-1 whitespace-pre-line ${sectionClass}`} style={delay()}>{model.summary}</p>

          {model.findings.length > 0 && (
            <section className={`mt-9 ${sectionClass}`} style={delay()} aria-labelledby="findings-heading">
              <h2 id="findings-heading" className="r-heading text-ink">Key findings</h2>
              <div className="mt-[13px] flex flex-col">
                {model.findings.map((finding, index) => (
                  <div key={index}>
                    <div className="finding" data-anchor={`f${index}`} data-active={finding.claim && activeClaim === finding.claim.claimId ? "true" : undefined}>
                      <p>
                        {finding.title && <strong>{finding.title.replace(/\.$/, "")}.</strong>} {finding.detail}
                        {finding.claim && (
                          <span className="whitespace-nowrap">
                            {" "}
                            <Markers claim={finding.claim} selection={selection} onSelect={onSelect} />
                          </span>
                        )}
                      </p>
                    </div>
                    {chartsFor(finding.claim)}
                  </div>
                ))}
              </div>
            </section>
          )}

          {model.otherClaims.length > 0 && (
            <section className={`mt-[23px] ${sectionClass}`} style={delay()} aria-labelledby="claims-heading">
              <h2 id="claims-heading" className="r-heading text-ink">{model.findings.length ? "Also supported" : "Supported claims"}</h2>
              <div className="mt-[13px] flex flex-col">
                {model.otherClaims.map((claim, index) => (
                  <div key={`${claim.claimId}-${index}`}>
                    <div className="finding" data-anchor={`o${index}`} data-active={activeClaim === claim.claimId ? "true" : undefined}>
                      <p className="!text-ink">
                        {claim.statement}{" "}
                        <span className="whitespace-nowrap"><Markers claim={claim} selection={selection} onSelect={onSelect} /></span>
                      </p>
                    </div>
                    {chartsFor(claim)}
                  </div>
                ))}
              </div>
            </section>
          )}

          {model.recommendations.length > 0 && (
            <section className={`mt-[23px] ${sectionClass}`} style={delay()} aria-labelledby="actions-heading">
              <h2 id="actions-heading" className="r-heading text-ink">Recommended actions</h2>
              <ol className="mt-2.5">
                {model.recommendations.map((item, index) => (
                  <li key={item.recommendation_id || index} className="action-row">
                    <span className="num" data-cited={item.cited} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <p>{item.action || item.title}</p>
                      {item.action && item.title && item.title !== item.action && <p className="action-note">{item.title}</p>}
                      {!item.cited && <p className="action-note">Not linked to a claim with verified citations.</p>}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <details className={`ledger-disclosure mt-[22px] ${sectionClass}`} style={delay()}>
            <summary>
              <span>What we couldn’t support</span>
              <span>
                {plural(rejectedClaims, "rejected claim")} · {plural(uncitedEvidence, "evidence passage")} not cited
              </span>
            </summary>
            <div className="border-t border-line px-4 py-3">
              {model.unsupported.length === 0 && uncitedEvidence === 0 && <p className="t-body text-ink-2">Nothing was set aside.</p>}
              {model.unsupported.length > 0 && (
                <ul className="flex flex-col gap-3">
                  {model.unsupported.map((item, index) => (
                    <li key={index}>
                      <p className="t-meta text-ink-3">{{ claim: "Rejected claim", inference: "Rejected inference", recommendation: "Rejected recommendation", warning: "Missing data", contradiction: "Unresolved contradiction" }[item.kind]}</p>
                      <p className="t-body text-ink">{item.text}</p>
                      {item.reasons.length > 0 && (
                        <ul className="mt-1">
                          {item.reasons.map((reason) => (
                            <li key={reason} className="t-meta text-ink-2">
                              {explainReason(reason)} <span className="mono text-ink-3">{reason.split(":")[0]}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {uncitedEvidence > 0 && (
                <p className="t-meta mt-3 text-ink-3">
                  {plural(uncitedEvidence, "passage")} {uncitedEvidence === 1 ? "was" : "were"} retrieved as evidence but not cited by any claim. They stay neutral on the tracks.
                </p>
              )}
            </div>
          </details>

          {model.citationOrder.length > 0 && (
            <details className="ledger-disclosure mt-3">
              <summary>
                <span>Passages used</span>
                <span>{plural(model.citationOrder.length, "passage")}</span>
              </summary>
              <ol className="border-t border-line px-4 py-3">
                {model.citationOrder.map((chunkId, index) => {
                  const passage = model.passages.get(chunkId)!;
                  const map = passage.sourceId ? outlines[passage.sourceId] : undefined;
                  return (
                    <li key={chunkId} className="py-1">
                      <button type="button" className="t-body text-left text-ink-2 hover:text-ink" onClick={() => onSelect({ kind: "passage", chunkId })}>
                        <span className="cite mr-2" aria-hidden="true">{index + 1}</span>
                        {passage.sourceName} · {passageLocatorLabel(passage, map)}
                        {(model.citedBy.get(chunkId)?.length ?? 0) > 1 && <span className="t-meta text-ink-3"> · cited by claims {model.citedBy.get(chunkId)!.join(", ")}</span>}
                      </button>
                    </li>
                  );
                })}
              </ol>
            </details>
          )}
        </div>
        <div className="brief-margin" aria-hidden={sidenotes.length === 0 || undefined}>
          {sidenotes.length > 0 && (
            <Sidenotes items={sidenotes} model={model} outlines={outlines} gridRef={gridRef} selection={selection} onSelect={onSelect} animate={fold} />
          )}
        </div>
      </div>
    </article>
  );
}
