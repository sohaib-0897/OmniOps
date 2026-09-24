"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import type { PassageMap } from "@/types/api";
import {
  keyboardStops,
  layoutTrack,
  trackPaths,
  trackTicks,
  unitAt,
  unitLabel,
  type PassageState,
  type TrackUnit,
} from "@/lib/source-track";

export interface SourceTrackProps {
  map: PassageMap;
  /** Accessible name, usually the file name. */
  label: string;
  states?: ReadonlyMap<string, PassageState>;
  focusChunkId?: string | null;
  citedBy?: ReadonlyMap<string, number[]>;
  height?: number;
  gap?: number;
  minSegment?: number;
  /** Fallback width before measurement (and for server rendering). */
  initialWidth?: number;
  ticks?: boolean;
  /** Indexed passages drawn full height (empty shelf, Home inventory). */
  indexedFull?: boolean;
  /** Evidence segments grow in document order (batch arrival). */
  grow?: boolean;
  /** Decorative tracks are hidden from assistive technology and not focusable. */
  decorative?: boolean;
  orientation?: "horizontal" | "vertical";
  onSelectPassage?: (chunkId: string) => void;
  className?: string;
}

export function sliceMap(map: PassageMap, start: number, end: number): PassageMap {
  return {
    ...map,
    passage_count: end - start,
    chunk_id: map.chunk_id.slice(start, end),
    chunk_index: map.chunk_index.slice(start, end),
    char_length: map.char_length.slice(start, end),
    page_number: map.page_number.slice(start, end),
    audio_start_ms: map.audio_start_ms.slice(start, end),
    audio_end_ms: map.audio_end_ms.slice(start, end),
    heading: map.heading.slice(start, end),
  };
}

function useMeasuredLength(initial: number, vertical: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [length, setLength] = useState(initial);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const size = vertical ? entry.contentRect.height : entry.contentRect.width;
      if (size > 0) setLength(Math.floor(size));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [vertical]);
  return { ref, length };
}

export function SourceTrack({
  map,
  label,
  states,
  focusChunkId = null,
  citedBy,
  height = 6,
  gap = 1,
  minSegment = 3,
  initialWidth = 552,
  ticks = false,
  indexedFull = false,
  grow = false,
  decorative = false,
  orientation = "horizontal",
  onSelectPassage,
  className,
}: SourceTrackProps) {
  const vertical = orientation === "vertical";
  const { ref, length } = useMeasuredLength(initialWidth, vertical);
  const layout = useMemo(
    () => layoutTrack(map, { width: length, gap, minSegment, states, focusChunkId }),
    [map, length, gap, minSegment, states, focusChunkId],
  );
  const paths = useMemo(() => trackPaths(layout, height, { indexedFull }), [layout, height, indexedFull]);
  const tickList = useMemo(() => (ticks && !vertical ? trackTicks(map, layout) : []), [ticks, vertical, map, layout]);
  const stops = useMemo(() => keyboardStops(layout), [layout]);
  const [active, setActive] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [zoom, setZoom] = useState<TrackUnit | null>(null);
  const liveId = useId();

  const counts = useMemo(() => {
    let evidence = 0;
    let cited = 0;
    map.chunk_id.forEach((id) => {
      const state = states?.get(id);
      if (state === "cited") cited += 1;
      if (state && state !== "indexed") evidence += 1;
    });
    return { evidence, cited };
  }, [map, states]);

  const summary = [
    `${label}: ${map.passage_count.toLocaleString("en-US")} ${map.passage_count === 1 ? "passage" : "passages"} indexed`,
    counts.evidence ? `${counts.evidence} retrieved as evidence` : null,
    counts.cited ? `${counts.cited} cited` : null,
    layout.binned ? "shown in groups" : null,
  ]
    .filter(Boolean)
    .join(", ");

  const selectUnit = (index: number) => {
    const unit = layout.units[index];
    if (!unit) return;
    if (unit.end - unit.start > 1) {
      setZoom(unit);
      return;
    }
    onSelectPassage?.(map.chunk_id[unit.start]);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!stops.length) return;
    const position = active == null ? -1 : stops.indexOf(active);
    let next: number | null = null;
    const forward = vertical ? "ArrowDown" : "ArrowRight";
    const backward = vertical ? "ArrowUp" : "ArrowLeft";
    if (event.key === forward) next = stops[Math.min(stops.length - 1, position + 1)];
    else if (event.key === backward) next = stops[Math.max(0, position <= 0 ? 0 : position - 1)];
    else if (event.key === "Home") next = stops[0];
    else if (event.key === "End") next = stops[stops.length - 1];
    else if ((event.key === "Enter" || event.key === " ") && active != null) {
      event.preventDefault();
      selectUnit(active);
      return;
    } else if (event.key === "Escape" && zoom) {
      setZoom(null);
      return;
    }
    if (next != null) {
      event.preventDefault();
      setActive(next);
    }
  };

  const pointerIndex = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const offset = vertical ? event.clientY - box.top : event.clientX - box.left;
    return unitAt(layout, offset);
  };

  const shown = hover ?? active;
  const shownUnit = shown != null ? layout.units[shown] : null;
  const svgWidth = vertical ? height + 10 : Math.max(1, length);
  const svgHeight = vertical ? Math.max(1, length) : height + (paths.dots.length ? 6 : 0);
  const transform = vertical ? "matrix(0 1 1 0 3 0)" : undefined;
  const interactive = !decorative;

  const svg = (
    <svg
      className={`track ${grow ? "track-grow" : ""}`}
      width={svgWidth}
      height={svgHeight}
      viewBox={`0 ${vertical ? 0 : 0} ${svgWidth} ${svgHeight}`}
      aria-hidden="true"
      focusable="false"
    >
      <g transform={transform}>
        {map.processing_status === "processing" || map.processing_status === "pending" ? (
          <rect className="pending" x="0.5" y="0.5" width={Math.max(0, length - 1)} height={height - 1} rx="2" />
        ) : null}
        <path className="indexed" d={paths.indexed} />
        <path className="evidence" d={paths.evidence} />
        <path className="cited" d={paths.cited} />
        {paths.dots.map((dot, index) => (
          <circle key={index} className="cited-dot" cx={dot.x} cy={height + 3.5} r="1.5" />
        ))}
        {paths.focus && <path className="focus-ring" d={paths.focus} />}
        {interactive && shownUnit && (
          <rect x={shownUnit.x - 1} y={-2} width={shownUnit.width + 2} height={height + 4} rx="2" fill="none" stroke="var(--ink-2)" strokeWidth="1" />
        )}
      </g>
    </svg>
  );

  if (decorative) {
    return (
      <div ref={ref} className={className} aria-hidden="true" style={vertical ? { height: "100%" } : undefined}>
        {svg}
      </div>
    );
  }

  const tooltipLeft = shownUnit ? shownUnit.x + shownUnit.width / 2 : 0;

  return (
    <div className={className} style={vertical ? { height: "100%" } : undefined}>
      <div
        ref={ref}
        className="track-wrap"
        role="group"
        tabIndex={0}
        aria-label={summary}
        aria-describedby={liveId}
        style={vertical ? { height: "100%", cursor: "pointer" } : { cursor: "pointer" }}
        onKeyDown={onKeyDown}
        onPointerMove={(event) => setHover(pointerIndex(event))}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setActive(null)}
        onClick={(event) => selectUnit(pointerIndex(event as unknown as PointerEvent<HTMLDivElement>))}
      >
        {svg}
        {shownUnit && !vertical && (
          <span className="track-tooltip" style={{ left: Math.min(Math.max(tooltipLeft, 60), Math.max(60, length - 60)) }} aria-hidden="true">
            {unitLabel(map, shownUnit, { citedBy })}
          </span>
        )}
        <span id={liveId} className="sr-only" aria-live="polite">
          {active != null && layout.units[active] ? unitLabel(map, layout.units[active], { citedBy }) : ""}
        </span>
      </div>
      {tickList.length > 0 && (
        <div className="track-ticks" aria-hidden="true">
          {tickList.map((tick) => (
            <span key={`${tick.x}-${tick.label}`} className="track-tick" style={{ left: tick.x }}>
              {tick.label}
            </span>
          ))}
        </div>
      )}
      {zoom && (
        <div className="mt-3 rounded-control border border-line p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="t-meta text-ink-3">{unitLabel(map, zoom, { citedBy })}</span>
            <button type="button" className="t-meta text-ink-2 hover:text-ink" onClick={() => setZoom(null)}>
              Close
            </button>
          </div>
          <SourceTrack
            map={sliceMap(map, zoom.start, zoom.end)}
            label={`${label}, passages ${zoom.start + 1} to ${zoom.end}`}
            states={states}
            focusChunkId={focusChunkId}
            citedBy={citedBy}
            height={height}
            minSegment={2}
            initialWidth={length}
            onSelectPassage={onSelectPassage}
          />
        </div>
      )}
    </div>
  );
}

/** Spreadsheets are not passages: one block per table, sized by row count. */
export function TableBlocks({
  tables,
  used,
  decorative = false,
  height = 6,
}: {
  tables: Array<{ id: string; table_name: string; row_count: number }>;
  used?: ReadonlySet<string>;
  decorative?: boolean;
  height?: number;
}) {
  const total = tables.reduce((sum, table) => sum + Math.max(1, table.row_count), 0) || 1;
  return (
    <div aria-hidden={decorative || undefined}>
      <div className="table-blocks">
        {tables.map((table) => (
          <span
            key={table.id}
            className="table-block"
            data-used={used?.has(table.id) || undefined}
            style={{ flexGrow: Math.max(1, table.row_count) / total, height }}
          />
        ))}
      </div>
      {!decorative && (
        <div className="table-labels">
          {tables.map((table) => (
            <span key={table.id} style={{ flexGrow: Math.max(1, table.row_count) / total }}>
              {table.table_name} · {table.row_count.toLocaleString("en-US")} rows
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
