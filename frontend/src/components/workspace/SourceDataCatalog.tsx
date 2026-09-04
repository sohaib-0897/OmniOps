"use client";

import React, { useState, useEffect } from "react";
import { SourceDocument, TabularDataset } from "@/types/api";
import {
  FileText,
  Table as TableIcon,
  Mic,
  Image as ImageIcon,
  FileCode,
  Trash2,
  Eye,
  Database,
  Search,
  AlertTriangle,
  FolderOpen,
  X,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

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
  const [searchTerm, setSearchTerm] = useState("");
  const [deletingFile, setDeletingFile] = useState<SourceDocument | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && deletingFile) {
        setDeletingFile(null);
      }
    };
    if (deletingFile) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deletingFile]);

  const getModalityIcon = (modality: string) => {
    switch (modality.toLowerCase()) {
      case "pdf":
        return (
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
            <FileText className="w-4 h-4" />
          </div>
        );
      case "spreadsheet":
      case "csv":
      case "xlsx":
        return (
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
            <TableIcon className="w-4 h-4" />
          </div>
        );
      case "audio":
        return (
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
            <Mic className="w-4 h-4" />
          </div>
        );
      case "image":
        return (
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
            <ImageIcon className="w-4 h-4" />
          </div>
        );
      default:
        return (
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
            <FileCode className="w-4 h-4" />
          </div>
        );
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingFile) return;
    setIsDeleting(true);
    try {
      await apiClient.delete(`/workspaces/${workspaceId}/files/${deletingFile.id}`);
      onRefresh();
    } catch (err) {
      console.error("Failed to delete file:", err);
    } finally {
      setIsDeleting(false);
      setDeletingFile(null);
    }
  };

  const filteredTables = tables.filter((t) =>
    t.table_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredFiles = files.filter((f) =>
    f.file_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const totalSources = files.length + tables.length;

  return (
    <div className="space-y-4 font-sans">
      {/* Search filter */}
      {totalSources > 2 && (
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search datasets and files..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-8 pr-3 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600 transition-colors"
          />
        </div>
      )}

      {/* Global Empty State */}
      {totalSources === 0 && (
        <div className="p-5 rounded-xl border border-dashed border-zinc-800 bg-zinc-950 text-center space-y-2">
          <div className="w-9 h-9 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-400 flex items-center justify-center mx-auto">
            <FolderOpen className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider">No Lakehouse Sources</h4>
            <p className="text-[11px] text-zinc-400 mt-0.5 max-w-xs mx-auto leading-relaxed">
              Upload spreadsheets and documents for analysis. Audio/image semantics require a configured provider.
            </p>
          </div>
        </div>
      )}

      {/* 1. Tabular Datasets Section */}
      {tables.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between pb-1">
            <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-zinc-400" />
              Tabular Datasets ({tables.length})
            </h3>
            <span className="text-[10px] font-mono text-zinc-400 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded font-semibold">
              DuckDB
            </span>
          </div>

          <div className="space-y-1.5">
            {filteredTables.map((table) => (
              <div
                key={table.id}
                role="button"
                tabIndex={0}
                onClick={() => onPreviewTable(table)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onPreviewTable(table);
                  }
                }}
                className="group flex items-center justify-between p-2.5 rounded-xl border border-zinc-800/90 bg-zinc-900/60 hover:bg-zinc-900 hover:border-zinc-700 cursor-pointer transition-all outline-none focus-visible:ring-1 focus-visible:ring-zinc-400"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center shrink-0">
                    <TableIcon className="w-3.5 h-3.5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-zinc-200 truncate group-hover:text-white transition-colors">
                      {table.table_name}
                    </p>
                    <p className="text-[10px] text-zinc-400 font-mono mt-0.5">
                      {table.row_count.toLocaleString()} rows • {table.column_count} cols
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  aria-label="Preview Table"
                  onClick={(e) => {
                    e.stopPropagation();
                    onPreviewTable(table);
                  }}
                  className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all cursor-pointer"
                  title="Inspect Schema & Sample Rows"
                >
                  <Eye className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. Source Documents Section */}
      {files.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between pb-1">
            <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-zinc-400" />
              Source Files ({files.length})
            </h3>
            <span className="text-[10px] font-mono text-zinc-400 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded font-semibold">
              Indexed
            </span>
          </div>

          <div className="space-y-1.5">
            {filteredFiles.map((file) => (
              <div
                key={file.id}
                role="button"
                tabIndex={0}
                onClick={() => onPreviewFile(file)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onPreviewFile(file);
                  }
                }}
                className="group flex items-center justify-between p-2.5 rounded-xl border border-zinc-800/90 bg-zinc-900/60 hover:bg-zinc-900 hover:border-zinc-700 cursor-pointer transition-all outline-none focus-visible:ring-1 focus-visible:ring-zinc-400"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {getModalityIcon(file.modality)}
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-zinc-200 truncate group-hover:text-white transition-colors">
                      {file.file_name}
                    </p>
                    <p className="text-[10px] text-zinc-400 uppercase font-mono mt-0.5">
                      {file.modality} • {(file.byte_size / 1024).toFixed(0)} KB
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label="Preview File"
                    onClick={(e) => {
                      e.stopPropagation();
                      onPreviewFile(file);
                    }}
                    className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all cursor-pointer"
                    title="Preview Extracted Chunks"
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label="Delete File"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingFile(file);
                    }}
                    className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all cursor-pointer"
                    title="Delete File"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Accessible Confirmation Modal */}
      {deletingFile && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setDeletingFile(null);
            }
          }}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 cursor-pointer"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-zinc-950 border border-zinc-800 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4 cursor-default"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0">
                  <AlertTriangle className="w-4 h-4 text-zinc-300" />
                </div>
                <div>
                  <h4 id="delete-dialog-title" className="text-xs font-bold text-white">
                    Delete Source File?
                  </h4>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Permanent removal from workspace index.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDeletingFile(null)}
                className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-850 transition-colors cursor-pointer"
                aria-label="Close dialog"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 text-xs font-medium text-zinc-200 truncate">
              {deletingFile.file_name}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setDeletingFile(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleConfirmDelete}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold text-black bg-white hover:bg-zinc-200 transition-colors cursor-pointer"
              >
                {isDeleting ? "Deleting..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
