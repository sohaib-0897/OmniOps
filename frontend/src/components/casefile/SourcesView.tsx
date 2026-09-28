"use client";

import { useState } from "react";
import { AudioLines, Eye, FileImage, FileSpreadsheet, FileText, Trash2 } from "lucide-react";
import type { PassageMap, SourceDocument, TabularDataset, Workspace } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { formatBytes, formatDate } from "@/lib/utils";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorState } from "@/components/ui/Primitives";
import { FileUploadZone } from "@/components/workspace/FileUploadZone";
import { SourceRow } from "./SourceRow";

export function SourcesView({
  workspace,
  files,
  tables,
  outlines,
  canEdit,
  onRefresh,
  onPreviewFile,
  onPreviewTable,
}: {
  workspace: Workspace;
  files: SourceDocument[];
  tables: TabularDataset[];
  outlines: Record<string, PassageMap>;
  canEdit: boolean;
  onRefresh: () => void;
  onPreviewFile: (file: SourceDocument) => void;
  onPreviewTable: (table: TabularDataset) => void;
}) {
  const [deleting, setDeleting] = useState<SourceDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passages = files.reduce((sum, file) => sum + (outlines[file.id]?.passage_count ?? 0), 0);

  const remove = async () => {
    if (!deleting || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.delete(`/workspaces/${workspace.id}/files/${deleting.id}`);
      onRefresh();
      setDeleting(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The source could not be removed. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rev-sources mx-auto w-full max-w-[1050px] pb-20">
      <p className="t-meta text-ink-3">{workspace.name} / Sources</p>
      <h1 className="rev-sources-title mt-3 text-ink">A collection of material.</h1>
      <p className="t-body mt-1 text-ink-2">
        {files.length} {files.length === 1 ? "source" : "sources"} · {passages.toLocaleString("en-US")} indexed {passages === 1 ? "passage" : "passages"} · {tables.length} {tables.length === 1 ? "table" : "tables"}
      </p>

      {canEdit && (
        <div className="mt-6">
          <FileUploadZone workspaceId={workspace.id} onUploadComplete={onRefresh} compact={files.length > 0} />
        </div>
      )}

      <ul className="rev-source-grid mt-8">
        {files.length === 0 && <li className="t-body py-6 text-ink-2">No sources yet. Upload a document, spreadsheet, image or audio file.</li>}
        {files.map((file) => {
          const fileTables = tables.filter((table) => table.source_id === file.id);
          return (
            <li key={file.id} className="rev-source-card">
              <div className="rev-source-cover" data-modality={file.modality} aria-hidden="true"><span>{file.modality === "spreadsheet" ? <FileSpreadsheet/> : file.modality === "audio" ? <AudioLines/> : file.modality === "image" ? <FileImage/> : <FileText/>}</span><i/><i/><i/><i/></div>
              <div className="rev-source-info">
              <SourceRow file={file} map={outlines[file.id]} tables={fileTables} ticks height={8} indexedFull showIcon onSelectPassage={() => onPreviewFile(file)} />
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="t-meta text-ink-3">{formatBytes(file.byte_size, 1)} · added {formatDate(file.created_at)}</span>
                {file.error_message && <span className="t-meta text-critical">{file.error_message}</span>}
                <span className="flex-1" />
                {file.modality === "spreadsheet"
                  ? fileTables.map((table) => (
                      <button key={table.id} type="button" className="btn-ghost h-7 px-2" onClick={() => onPreviewTable(table)}>
                        <Eye className="h-3.5 w-3.5" aria-hidden="true" /> {table.table_name}
                      </button>
                    ))
                  : (
                      <button type="button" className="btn-ghost h-7 px-2" onClick={() => onPreviewFile(file)} disabled={!["ready", "partially_ready"].includes(file.processing_status)}>
                        <Eye className="h-3.5 w-3.5" aria-hidden="true" /> Read passages
                      </button>
                    )}
                {canEdit && (
                  <button type="button" className="btn-ghost h-7 px-2 hover:!text-critical" onClick={() => { setDeleting(file); setError(null); }} aria-label={`Delete ${file.file_name}`}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Delete
                  </button>
                )}
              </div>
              </div>
            </li>
          );
        })}
      </ul>

      <Dialog compact open={Boolean(deleting)} onClose={() => setDeleting(null)} title="Delete source" description="This permanently removes the file, its passages and its evidence." busy={busy}>
        <div className="space-y-4">
          <p className="t-body text-ink-2">
            Claims that cite <strong className="text-ink">{deleting?.file_name}</strong> will be marked rejected with a note that their source was deleted. Saved briefs keep their text.
          </p>
          {error && <ErrorState message={error} />}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setDeleting(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-destructive" onClick={() => void remove()} disabled={busy}>{busy ? "Deleting…" : "Delete source"}</button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
