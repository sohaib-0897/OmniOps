"use client";

import React, { useEffect, useState } from "react";
import { TabularDataset, TablePreview } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { X, Table as TableIcon, Loader2, Search, Copy, Check } from "lucide-react";

interface Props {
  table: TabularDataset | null;
  onClose: () => void;
}

export function TabularPreviewModal({ table, onClose }: Props) {
  const [preview, setPreview] = useState<TablePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [columnSearch, setColumnSearch] = useState("");
  const [copiedCol, setCopiedCol] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (!table) {
      setPreview(null);
      return;
    }

    setLoading(true);
    apiClient
      .get<TablePreview>(`/workspaces/${table.workspace_id}/tables/${table.id}/preview`)
      .then((data) => setPreview(data))
      .catch((err) => console.error("Failed to load table preview:", err))
      .finally(() => setLoading(false));
  }, [table]);

  if (!table) return null;

  const filteredColumns = preview?.schema_definition.filter((col) =>
    col.name.toLowerCase().includes(columnSearch.toLowerCase())
  ) || [];

  const handleCopyColumns = async () => {
    if (!preview) return;
    const cols = preview.columns.join(", ");
    await navigator.clipboard.writeText(cols);
    setCopiedCol(true);
    setTimeout(() => setCopiedCol(false), 2000);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="table-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 font-sans cursor-pointer"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-4xl max-h-[85vh] shadow-2xl flex flex-col overflow-hidden cursor-default"
      >
        {/* Header */}
        <div className="p-4 border-b border-zinc-850 flex items-center justify-between bg-black">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center font-bold">
              <TableIcon className="w-4 h-4" />
            </div>
            <div>
              <h3 id="table-modal-title" className="text-sm font-bold text-white font-mono">{table.table_name}</h3>
              <p className="text-[11px] text-zinc-400 font-mono">
                {table.row_count.toLocaleString()} rows • {table.column_count} columns (Vectorized Parquet)
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopyColumns}
              className="text-xs text-zinc-400 hover:text-white inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-zinc-900 border border-zinc-800 transition-colors cursor-pointer"
              title="Copy Column Names List"
            >
              {copiedCol ? <Check className="w-3.5 h-3.5 text-white" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedCol ? "Copied" : "Copy Columns"}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close table preview"
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 flex-1 overflow-y-auto space-y-4 text-xs">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2 text-zinc-500">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
              <span>Loading schema profile and preview rows...</span>
            </div>
          ) : preview ? (
            <>
              {/* Column Schema Profile */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider block">
                    Column Profiling ({preview.schema_definition.length})
                  </span>
                  <div className="relative w-48">
                    <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-zinc-500" />
                    <input
                      type="text"
                      placeholder="Filter columns..."
                      value={columnSearch}
                      onChange={(e) => setColumnSearch(e.target.value)}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-8 pr-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600"
                    />
                  </div>
                </div>

                <div className="border border-zinc-800 rounded-xl overflow-hidden max-h-56 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-zinc-900 text-xs font-semibold text-zinc-300 border-b border-zinc-800 sticky top-0 font-mono">
                      <tr>
                        <th className="p-2">Column Name</th>
                        <th className="p-2">Type</th>
                        <th className="p-2">Null %</th>
                        <th className="p-2">Unique</th>
                        <th className="p-2">Sample Values</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-850">
                      {filteredColumns.map((col, idx) => (
                        <tr key={idx} className="hover:bg-zinc-900/50 transition-colors">
                          <td className="p-2 font-mono font-semibold text-zinc-200">{col.name}</td>
                          <td className="p-2 font-mono text-[11px] text-zinc-400">{col.type}</td>
                          <td className="p-2 font-mono text-zinc-400">{col.null_percentage}%</td>
                          <td className="p-2 font-mono text-zinc-400">{col.unique_count}</td>
                          <td className="p-2 text-zinc-400 truncate max-w-xs font-mono text-[11px]">
                            {col.sample_values.join(", ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Sample Data Rows */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider block">
                  Sample Data Rows (Top 50 Rows)
                </span>
                <div className="border border-zinc-800 rounded-xl overflow-x-auto max-h-64">
                  <table className="w-full text-left border-collapse whitespace-nowrap">
                    <thead className="bg-zinc-900 text-xs font-semibold text-zinc-300 border-b border-zinc-800 sticky top-0 font-mono">
                      <tr>
                        {preview.columns.map((col, idx) => (
                          <th key={idx} className="p-2 font-mono">{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-850">
                      {preview.sample_rows.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-zinc-900/50 transition-colors">
                          {preview.columns.map((col, cIdx) => (
                            <td key={cIdx} className="p-2 font-mono text-[11px] text-zinc-300">
                              {String(row[col] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
