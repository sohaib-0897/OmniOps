/**
 * Source track geometry. Pure functions only: the renderer draws what these
 * return, and the unit tests exercise them without a DOM.
 *
 * One segment per indexed passage, ordered by chunk_index, with width
 * proportional to the passage's character length. When passages cannot each
 * get a legible segment the track switches to truthful bins: every bin is a
 * contiguous chunk_index range whose width equals its total length, and whose
 * state is the strongest state inside it.
 */
import type { PassageMap } from "@/types/api";

export type PassageState = "indexed" | "evidence" | "cited";

const STATE_RANK: Record<PassageState, number> = { indexed: 0, evidence: 1, cited: 2 };

export interface TrackUnit {
  /** First passage position (0-based index into the map's columns). */
  start: number;
  /** One past the last passage position. */
  end: number;
  x: number;
  width: number;
  state: PassageState;
  focused: boolean;
  citedCount: number;
  evidenceCount: number;
}

export interface TrackLayout {
  units: TrackUnit[];
  binned: boolean;
  width: number;
}

export interface TrackOptions {
  width: number;
  gap?: number;
  /** Minimum legible segment width. Below it the track bins. */
  minSegment?: number;
  states?: ReadonlyMap<string, PassageState>;
  focusChunkId?: string | null;
}

export function passageState(
  map: PassageMap,
  position: number,
  states?: ReadonlyMap<string, PassageState>,
): PassageState {
  return states?.get(map.chunk_id[position]) ?? "indexed";
}

function strongest(a: PassageState, b: PassageState): PassageState {
  return STATE_RANK[b] > STATE_RANK[a] ? b : a;
}

/** Split passages into `count` contiguous ranges of roughly equal total length. */
export function binRanges(lengths: readonly number[], count: number): Array<[number, number]> {
  const n = lengths.length;
  if (n === 0) return [];
  const bins = Math.max(1, Math.min(count, n));
  const total = lengths.reduce((sum, value) => sum + Math.max(1, value), 0);
  const ranges: Array<[number, number]> = [];
  let start = 0;
  let consumed = 0;
  for (let bin = 0; bin < bins; bin += 1) {
    const remainingBins = bins - bin;
    if (bin === bins - 1) {
      ranges.push([start, n]);
      break;
    }
    const target = (total * (bin + 1)) / bins;
    let end = start;
    // Each bin takes at least one passage and leaves one per remaining bin.
    do {
      consumed += Math.max(1, lengths[end]);
      end += 1;
    } while (end < n - (remainingBins - 1) && consumed + Math.max(1, lengths[end] ?? 0) / 2 < target);
    ranges.push([start, end]);
    start = end;
  }
  return ranges;
}

export function layoutTrack(map: PassageMap, options: TrackOptions): TrackLayout {
  const width = Math.max(0, options.width);
  const gap = options.gap ?? 1;
  const minSegment = options.minSegment ?? 3;
  const n = map.passage_count;
  if (n === 0 || width === 0) return { units: [], binned: false, width };

  const lengths = map.char_length.map((value) => Math.max(1, value || 0));
  const capacity = Math.max(1, Math.floor((width + gap) / (minSegment + gap)));
  const binned = n > capacity;
  const ranges: Array<[number, number]> = binned
    ? binRanges(lengths, capacity)
    : lengths.map((_, index) => [index, index + 1]);

  const rangeLengths = ranges.map(([start, end]) => {
    let sum = 0;
    for (let i = start; i < end; i += 1) sum += lengths[i];
    return sum;
  });
  const total = rangeLengths.reduce((sum, value) => sum + value, 0);
  const available = Math.max(0, width - gap * (ranges.length - 1));
  // A small floor keeps very short passages visible; the rest is proportional.
  const floor = Math.min(binned ? minSegment : 1, available / ranges.length);
  const spare = Math.max(0, available - floor * ranges.length);

  const units: TrackUnit[] = [];
  let x = 0;
  ranges.forEach(([start, end], index) => {
    const unitWidth = floor + (spare * rangeLengths[index]) / total;
    let state: PassageState = "indexed";
    let citedCount = 0;
    let evidenceCount = 0;
    let focused = false;
    for (let i = start; i < end; i += 1) {
      const current = passageState(map, i, options.states);
      state = strongest(state, current);
      if (current === "cited") citedCount += 1;
      if (current !== "indexed") evidenceCount += 1;
      if (options.focusChunkId && map.chunk_id[i] === options.focusChunkId) focused = true;
    }
    units.push({ start, end, x, width: unitWidth, state, focused, citedCount, evidenceCount });
    x += unitWidth + gap;
  });
  return { units, binned, width };
}

/** Binary search over cumulative offsets: which unit sits under `x`? */
export function unitAt(layout: TrackLayout, x: number): number {
  const { units } = layout;
  if (units.length === 0) return -1;
  let low = 0;
  let high = units.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (units[mid].x <= x) low = mid;
    else high = mid - 1;
  }
  return low;
}

function rect(x: number, y: number, w: number, h: number): string {
  const r = Math.min(1.5, w / 2, h / 2);
  if (w <= 2 * r + 0.01) return `M${x.toFixed(2)} ${y}h${w.toFixed(2)}v${h}h${(-w).toFixed(2)}Z`;
  return `M${(x + r).toFixed(2)} ${y}h${(w - 2 * r).toFixed(2)}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${(-(w - 2 * r)).toFixed(2)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}Z`;
}

export interface TrackPaths {
  indexed: string;
  evidence: string;
  cited: string;
  focus: string;
  dots: Array<{ x: number }>;
}

/**
 * One path per state keeps the DOM at a handful of nodes at any passage count.
 * Shape carries state as well as colour: indexed is half height, evidence and
 * cited are full height, cited adds a dot, focus adds an outline.
 */
export function trackPaths(
  layout: TrackLayout,
  height: number,
  { indexedFull = false }: { indexedFull?: boolean } = {},
): TrackPaths {
  const half = Math.max(2, Math.round(height / 2));
  const paths = { indexed: "", evidence: "", cited: "", focus: "" };
  const dots: Array<{ x: number }> = [];
  for (const unit of layout.units) {
    if (unit.state === "indexed") {
      const h = indexedFull ? height : half;
      paths.indexed += rect(unit.x, (height - h) / 2, unit.width, h);
    } else {
      paths[unit.state] += rect(unit.x, 0, unit.width, height);
    }
    if (unit.citedCount > 0) dots.push({ x: unit.x + unit.width / 2 });
    if (unit.focused) paths.focus += rect(unit.x - 1.5, -1.5, unit.width + 3, height + 3);
  }
  return { ...paths, dots };
}

const integer = new Intl.NumberFormat("en-US");

export function formatTimestamp(ms: number | null | undefined): string | null {
  if (ms == null || !Number.isFinite(ms)) return null;
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

/** Short locator for one passage: page, timestamp or heading. */
export function passageLocator(map: PassageMap, position: number): string | null {
  const page = map.page_number[position];
  if (page != null) return `p.${page}`;
  const time = formatTimestamp(map.audio_start_ms[position]);
  if (time) return time;
  const heading = map.heading[position];
  return heading ? heading : null;
}

function range(values: Array<number | null>): string | null {
  const numbers = values.filter((value): value is number => value != null);
  if (numbers.length === 0) return null;
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  return min === max ? `p.${min}` : `p.${min}–${max}`;
}

export interface UnitLabelContext {
  citedBy?: ReadonlyMap<string, number[]>;
}

/** Hover and aria text. Positions are shown 1-based, as chunk order. */
export function unitLabel(map: PassageMap, unit: TrackUnit, context: UnitLabelContext = {}): string {
  const count = map.passage_count;
  if (unit.end - unit.start === 1) {
    const position = unit.start;
    const parts = [`Passage ${integer.format(position + 1)} of ${integer.format(count)}`];
    const page = map.page_number[position];
    if (page != null) parts.push(`page ${page}`);
    const time = formatTimestamp(map.audio_start_ms[position]);
    if (time) parts.push(time);
    const heading = map.heading[position];
    if (heading) parts.push(heading);
    const claims = context.citedBy?.get(map.chunk_id[position]);
    if (unit.state === "cited" && claims?.length) parts.push(`cited by ${claims.length > 1 ? "claims" : "claim"} ${claims.join(", ")}`);
    else if (unit.state === "cited") parts.push("cited");
    else if (unit.state === "evidence") parts.push("retrieved as evidence, not cited");
    return parts.join(", ");
  }
  const parts = [`Passages ${integer.format(unit.start + 1)}–${integer.format(unit.end)}`];
  const pages = range(map.page_number.slice(unit.start, unit.end));
  if (pages) parts.push(pages);
  if (unit.citedCount) parts.push(`${unit.citedCount} cited`);
  const uncited = unit.evidenceCount - unit.citedCount;
  if (uncited > 0) parts.push(`${uncited} evidence`);
  return parts.join(" · ");
}

export interface TrackTick {
  x: number;
  label: string;
}

/** Boundary ticks beneath a track: page, timestamp or heading changes. */
export function trackTicks(map: PassageMap, layout: TrackLayout, minSpacing = 28): TrackTick[] {
  const ticks: TrackTick[] = [];
  let previous: string | null = null;
  let lastX = -Infinity;
  let lastWidth = 0;
  // Labels are 10px text beside a 4px-padded tick: keep each clear of the previous one.
  const labelWidth = (label: string) => Math.ceil(label.length * 5.6) + 12;
  for (const unit of layout.units) {
    const page = map.page_number[unit.start];
    let key: string | null = null;
    let label: string | null = null;
    if (page != null) {
      key = `p${page}`;
      label = `p.${page}`;
    } else if (map.heading[unit.start]) {
      key = `h${map.heading[unit.start]}`;
      label = map.heading[unit.start]!.slice(0, 18);
    } else if (map.audio_start_ms[unit.start] != null) {
      const time = formatTimestamp(map.audio_start_ms[unit.start]);
      key = time;
      label = time;
    }
    if (key && key !== previous) {
      previous = key;
      if (unit.x - lastX >= Math.max(minSpacing, lastWidth) && label) {
        ticks.push({ x: unit.x, label });
        lastX = unit.x;
        lastWidth = labelWidth(label);
      }
    }
  }
  return ticks;
}

/**
 * Keyboard stops: evidence and cited units in document order. Arrow keys move
 * between them; Home/End jump to the ends.
 */
export function keyboardStops(layout: TrackLayout): number[] {
  const stops = layout.units
    .map((unit, index) => (unit.state !== "indexed" ? index : -1))
    .filter((index) => index >= 0);
  return stops.length ? stops : layout.units.map((_, index) => index);
}

export function positionOfChunk(map: PassageMap, chunkId: string): number {
  return map.chunk_id.indexOf(chunkId);
}
