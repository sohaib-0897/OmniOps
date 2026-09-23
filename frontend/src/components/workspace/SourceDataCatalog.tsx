"use client";
import { useMemo, useState } from "react";
import {
  FileText,
  Image as ImageIcon,
  Mic,
  Search,
  Table2,
  Trash2,
} from "lucide-react";
import { SourceDocument, TabularDataset } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { formatBytes, formatDate } from "@/lib/utils";
import {
  EmptyState,
  ErrorState,
  StatusBadge,
} from "@/components/ui/Primitives";
import { Dialog } from "@/components/ui/Dialog";

interface Props {
  workspaceId: string;
  files: SourceDocument[];
  tables: TabularDataset[];
  onRefresh: () => void;
  onPreviewFile: (file: SourceDocument) => void;
  onPreviewTable: (table: TabularDataset) => void;
}
export function SourceDataCatalog({
  workspaceId,
  files,
  tables,
  onRefresh,
  onPreviewFile,
  onPreviewTable,
}: Props) {
  const [search, setSearch] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [status, setStatus] = useState("all");
  const [deleting, setDeleting] = useState<SourceDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const query = search.toLowerCase().trim();
  const visible = useMemo(
    () =>
      files.filter(
        (file) =>
          file.file_name.toLowerCase().includes(query) &&
          (status === "all" || file.processing_status === status),
      ),
    [files, query, status],
  );
  const visibleTables = useMemo(
    () =>
      tables.filter((table) => table.table_name.toLowerCase().includes(query)),
    [tables, query],
  );
  const remove = async () => {
    if (!deleting || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.delete(`/workspaces/${workspaceId}/files/${deleting.id}`);
      onRefresh();
      setDeleting(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The source could not be removed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="section-title">Sources</h2>
        <span className="mono-copy">{files.length} {files.length === 1 ? "file" : "files"}</span>
      </div>
      {files.length > 0 && (
        <details open={files.length > 5 || filtersOpen || Boolean(search) || status !== "all"} onToggle={(event) => setFiltersOpen(event.currentTarget.open)} className="text-xs text-zinc-400">
          <summary className="mb-3">Search and filter sources</summary>
        <div className="space-y-2">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-3 h-3.5 w-3.5 text-zinc-400" />
            <input
              aria-label="Search sources"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search sources"
              className="field h-10 border-transparent bg-transparent pl-9 text-xs hover:border-zinc-700"
            />
          </label>
          <select
            aria-label="Filter source status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="field h-9 border-transparent bg-transparent text-xs text-zinc-400 hover:border-zinc-700"
          >
            <option value="all">All processing states</option>
            <option value="ready">Ready</option>
            <option value="partially_ready">Partially ready</option>
            <option value="processing">Processing</option>
            <option value="pending">Queued</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        </details>
      )}
      {files.length === 0 ? (
        <p className="py-3 text-sm leading-6 text-zinc-400">Your source material will appear here. Attach a document, spreadsheet, image, or audio file to begin.</p>
      ) : visible.length === 0 ? (
        <EmptyState
          title="No matching sources"
          description="Clear the search or change the processing filter."
          action={
            <button
              className="btn-secondary"
              onClick={() => {
                setSearch("");
                setStatus("all");
              }}
            >
              Clear filters
            </button>
          }
        />
      ) : (
        <div className="divide-y divide-zinc-800">
          {visible.map((file) => {
            const Icon =
              file.modality === "audio"
                ? Mic
                : file.modality === "image"
                  ? ImageIcon
                  : file.modality === "spreadsheet"
                    ? Table2
                    : FileText;
            return (
              <article key={file.id} className="directory-row group rounded-md px-1 py-3 hover:bg-zinc-800/40 focus-within:bg-zinc-800/40">
                <div className="flex items-start gap-2">
                  <Icon className="mt-1 h-4 w-4 shrink-0 text-zinc-400" />
                  <button
                    onClick={() => onPreviewFile(file)}
                    className="min-w-0 flex-1 text-left"
                    title={file.file_name}
                  >
                    <span className="block truncate text-sm font-medium text-zinc-200 group-hover:text-white">
                      {file.file_name}
                    </span>
                    <span className="mt-1 block text-[11px] capitalize text-zinc-400">
                      {file.modality} · {formatBytes(file.byte_size, 1)}
                    </span>
                  </button>
                  <button
                    onClick={() => {
                      setDeleting(file);
                      setError(null);
                    }}
                    className="btn-icon h-7 w-7 text-zinc-500 hover:text-red-300 group-hover:text-zinc-300 focus-visible:text-zinc-300"
                    aria-label={`Remove ${file.file_name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 pl-6">
                  <StatusBadge status={file.processing_status} />
                  <time
                    className="text-[11px] text-zinc-500"
                    title={new Date(file.created_at).toLocaleString()}
                  >
                    {formatDate(file.created_at)}
                  </time>
                </div>
                {file.error_message && (
                  <p className="mt-2 break-words pl-6 text-xs leading-5 text-amber-200">
                    {file.error_message}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}
      {tables.length > 0 && (
        <section className="border-t border-zinc-800 pt-4">
          <h3 className="eyebrow mb-3">Extracted tables · {tables.length}</h3>
          <div className="space-y-1">
            {visibleTables.map((table) => (
              <button
                key={table.id}
                onClick={() => onPreviewTable(table)}
                className="flex w-full items-start gap-2 rounded-md py-2 text-left hover:bg-zinc-800/50"
              >
                <Table2 className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-zinc-200">
                    {table.table_name}
                  </span>
                  <span className="mt-1 block text-[11px] text-zinc-400">
                    {table.row_count.toLocaleString()} rows ·{" "}
                    {table.column_count} columns
                  </span>
                </span>
              </button>
            ))}
            {visibleTables.length === 0 && (
              <p className="meta-copy">No tables match your search.</p>
            )}
          </div>
        </section>
      )}
      <Dialog
        compact
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        title="Remove source?"
        description="This removes the file from the workspace index. This action cannot be undone."
        busy={busy}
      >
        <p className="mb-4 break-words rounded-md border border-zinc-800 p-3 text-sm">
          {deleting?.file_name}
        </p>
        {error && <ErrorState message={error} />}
        <div className="mt-5 flex justify-end gap-2">
          <button
            disabled={busy}
            className="btn-secondary"
            onClick={() => setDeleting(null)}
          >
            Keep source
          </button>
          <button
            disabled={busy}
            className="btn-destructive"
            onClick={() => void remove()}
          >
            {busy ? "Removing" : "Remove source"}
          </button>
        </div>
      </Dialog>
    </div>
  );
}
