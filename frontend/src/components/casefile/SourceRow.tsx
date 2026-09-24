"use client";

import type { ReactNode } from "react";
import { Table2 } from "lucide-react";
import type { PassageMap, SourceDocument, TabularDataset } from "@/types/api";
import type { PassageState } from "@/lib/source-track";
import { formatTimestamp } from "@/lib/source-track";
import { SourceTrack, TableBlocks } from "./SourceTrack";

export function extensionLabel(file: Pick<SourceDocument, "file_name" | "modality">) {
  const extension = file.file_name.includes(".") ? file.file_name.split(".").pop()!.toUpperCase() : "";
  if (extension && extension.length <= 5) return extension;
  return file.modality.toUpperCase();
}

const plural = (count: number, one: string, many = `${one}s`) => `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;

/** Inventory line from real metadata only: pages, duration, passages, tables. */
export function sourceMeta(file: SourceDocument, map: PassageMap | undefined, tables: TabularDataset[]): string {
  const parts = [extensionLabel(file)];
  if (file.modality === "spreadsheet") {
    parts.push(plural(tables.length, "table"));
    const rows = tables.reduce((sum, table) => sum + table.row_count, 0);
    if (tables.length) parts.push(plural(rows, "row"));
    return parts.join(" · ");
  }
  if (map) {
    const pages = new Set(map.page_number.filter((value): value is number => value != null));
    if (pages.size) parts.push(plural(pages.size, "page"));
    const end = Math.max(0, ...map.audio_end_ms.filter((value): value is number => value != null));
    if (end > 0) parts.push(formatTimestamp(end)!);
    parts.push(plural(map.passage_count, "passage"));
  }
  return parts.join(" · ");
}

export interface SourceRowProps {
  file: SourceDocument;
  map?: PassageMap;
  tables: TabularDataset[];
  states?: ReadonlyMap<string, PassageState>;
  focusChunkId?: string | null;
  citedBy?: ReadonlyMap<string, number[]>;
  right?: ReactNode;
  ticks?: boolean;
  grow?: boolean;
  height?: number;
  indexedFull?: boolean;
  decorative?: boolean;
  compact?: boolean;
  showIcon?: boolean;
  /** Gap between the label line and the track (Figma: 10 on the shelf, 4 in the field). */
  labelGap?: number;
  padded?: boolean;
  onSelectPassage?: (chunkId: string) => void;
}

export function SourceRow({
  file,
  map,
  tables,
  states,
  focusChunkId,
  citedBy,
  right,
  ticks = false,
  grow = false,
  height = 6,
  indexedFull = false,
  decorative = false,
  compact = false,
  showIcon = false,
  labelGap = 10,
  padded = true,
  onSelectPassage,
}: SourceRowProps) {
  const processing = file.processing_status === "pending" || file.processing_status === "processing";
  const failed = file.processing_status === "failed";
  const spreadsheet = file.modality === "spreadsheet";
  const statusText = processing ? "Processing" : failed ? "Failed to process" : file.processing_status === "partially_ready" ? "Partially ready" : null;
  return (
    <div className={compact ? "pb-3.5 last:pb-0" : padded ? "py-2" : undefined}>
      <div className="flex items-baseline gap-3" style={{ marginBottom: compact ? 4 : labelGap }}>
        <span className={`flex min-w-0 flex-1 items-center gap-2 ${compact ? "t-meta text-ink-2" : "t-label text-ink"}`}>
          {showIcon && spreadsheet && <Table2 className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden="true" />}
          <span className="truncate" title={file.file_name}>{file.file_name}</span>
        </span>
        <span className={`t-meta shrink-0 ${failed ? "text-critical" : "text-ink-3"}`}>
          {right ?? statusText ?? sourceMeta(file, map, tables)}
        </span>
      </div>
      {spreadsheet ? (
        tables.length ? (
          <TableBlocks tables={tables} decorative={decorative || compact} height={height} />
        ) : (
          <div className="table-blocks" aria-hidden="true"><span className="table-block" style={{ flexGrow: 1, height, borderStyle: processing ? "dashed" : undefined }} /></div>
        )
      ) : map && map.passage_count > 0 ? (
        <SourceTrack
          map={map}
          label={file.file_name}
          states={states}
          focusChunkId={focusChunkId}
          citedBy={citedBy}
          height={height}
          ticks={ticks}
          grow={grow}
          indexedFull={indexedFull}
          decorative={decorative}
          onSelectPassage={onSelectPassage}
        />
      ) : (
        <div
          aria-hidden="true"
          style={{ height, borderRadius: 2, border: `1px dashed ${processing ? "var(--track-pending)" : "var(--line-strong)"}` }}
        />
      )}
      {!spreadsheet && map && map.passage_count === 0 && !processing && !decorative && (
        <p className="t-meta mt-1.5 text-ink-3">No passages were extracted from this source.</p>
      )}
    </div>
  );
}
