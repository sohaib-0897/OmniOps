"use client";

import { useEffect, useRef } from "react";
import type { PassageMap, SourceDocument, TabularDataset, Workspace } from "@/types/api";
import { FileUploadZone } from "@/components/workspace/FileUploadZone";
import { Composer, type ComposerHandle } from "./Composer";
import { SourceRow } from "./SourceRow";

const baseName = (name: string) => name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

/** Starter questions built only from real source names. */
function suggestions(files: SourceDocument[]) {
  const ready = files.filter((file) => ["ready", "partially_ready"].includes(file.processing_status));
  const document = ready.find((file) => file.modality !== "spreadsheet");
  const sheet = ready.find((file) => file.modality === "spreadsheet");
  const items: string[] = [];
  if (document) items.push(`Summarize ${baseName(document.file_name)}`);
  if (sheet) items.push(`What changed over time in ${sheet.file_name}?`);
  if (document && !sheet) items.push(`What are the main risks in ${baseName(document.file_name)}?`);
  return items;
}

export function scopeSummary(files: SourceDocument[], outlines: Record<string, PassageMap>, tables: TabularDataset[]) {
  const ready = files.filter((file) => ["ready", "partially_ready"].includes(file.processing_status));
  const passages = ready.reduce((sum, file) => sum + (outlines[file.id]?.passage_count ?? 0), 0);
  const tableCount = tables.filter((table) => ready.some((file) => file.id === table.source_id)).length;
  const parts: string[] = [];
  if (passages) parts.push(`${passages.toLocaleString("en-US")} ${passages === 1 ? "passage" : "passages"}`);
  if (tableCount) parts.push(`${tableCount} ${tableCount === 1 ? "table" : "tables"}`);
  return parts.length ? { label: `${parts.join(" · ")} in scope`, empty: false } : { label: "No ready sources yet", empty: true };
}

export function EmptyWorkspace({
  workspace,
  files,
  tables,
  outlines,
  submitting,
  onStart,
  onSourcesChanged,
  onManageSources,
  canEdit,
  prefill,
}: {
  workspace: Workspace;
  files: SourceDocument[];
  tables: TabularDataset[];
  outlines: Record<string, PassageMap>;
  submitting: boolean;
  onStart: (objective: string) => Promise<boolean>;
  onSourcesChanged: () => void;
  onManageSources: () => void;
  canEdit: boolean;
  prefill?: string | null;
}) {
  const composer = useRef<ComposerHandle>(null);
  useEffect(() => {
    if (prefill) composer.current?.setObjective(prefill);
  }, [prefill]);
  const scope = scopeSummary(files, outlines, tables);
  const starters = suggestions(files);
  return (
    <div className="rev-empty mx-auto w-full max-w-[880px] pb-20 pt-[90px] max-lg:pt-10">
      <p className="rev-workspace-label">{workspace.name}</p>
      <h1 className="rev-empty-title mt-5 text-ink">
        What do you want to investigate?
      </h1>
      <div className="mt-5">
        <Composer
          ref={composer}
          workspaceId={workspace.id}
          onStart={onStart}
          onSourcesChanged={onSourcesChanged}
          submitting={submitting}
          scopeLabel={scope.label}
          scopeEmpty={scope.empty}
          placeholder="Ask about revenue, retention, cost or risk…"
          canEdit={canEdit}
        />
      </div>
      {starters.length > 0 && canEdit && (
        <div className="mt-5 flex flex-wrap gap-2" aria-label="Suggested questions">
          {starters.map((text) => (
            <button key={text} type="button" className="suggestion" onClick={() => composer.current?.setObjective(text)}>
              {text}
            </button>
          ))}
        </div>
      )}

      <section className="rev-empty-sources mt-12" aria-labelledby="scope-heading">
        <div className="flex items-center justify-between border-b border-line pb-[18px]">
          <h2 id="scope-heading" className="t-label">Your material <span className="rev-material-count">{files.length}</span></h2>
          <button type="button" className="t-meta text-ink-2 hover:text-ink" onClick={onManageSources}>
            Manage sources →
          </button>
        </div>
        {files.length === 0 ? (
          <div className="mt-5">
            {canEdit ? (
              <FileUploadZone workspaceId={workspace.id} onUploadComplete={onSourcesChanged} />
            ) : (
              <p className="t-body text-ink-2">This workspace has no sources yet.</p>
            )}
          </div>
        ) : (
          <div className="rev-empty-source-list mt-2.5">
            {files.map((file) => (
              <SourceRow
                key={file.id}
                file={file}
                map={outlines[file.id]}
                tables={tables.filter((table) => table.source_id === file.id)}
                height={10}
                indexedFull
                ticks
              />
            ))}
            <p className="t-meta mt-2.5 text-ink-3">
              Each segment is one indexed passage, sized to its length. Spreadsheets are queried with SQL and appear as tables. An answer lights up the passages its claims cite, once each citation has been checked against its passage.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
