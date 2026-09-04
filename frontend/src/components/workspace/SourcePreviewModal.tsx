"use client";

import React, { useEffect, useState } from "react";
import { SourceDocument, DocumentChunk } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { X, FileText, Loader2, Bookmark, Search, Copy, Check } from "lucide-react";

interface Props {
  file: SourceDocument | null;
  onClose: () => void;
}

export function SourcePreviewModal({ file, onClose }: Props) {
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [chunkSearch, setChunkSearch] = useState("");
  const [copiedChunkId, setCopiedChunkId] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (!file) {
      setChunks([]);
      return;
    }

    setLoading(true);
    apiClient
      .get<DocumentChunk[]>(`/workspaces/${file.workspace_id}/files/${file.id}/preview`)
      .then((data) => setChunks(data))
      .catch((err) => console.error("Failed to load chunks:", err))
      .finally(() => setLoading(false));
  }, [file]);

  if (!file) return null;

  const filteredChunks = chunks.filter((c) =>
    c.content.toLowerCase().includes(chunkSearch.toLowerCase())
  );

  const handleCopyChunk = async (chunk: DocumentChunk) => {
    try {
      await navigator.clipboard.writeText(chunk.content);
      setCopiedChunkId(chunk.id);
      setTimeout(() => setCopiedChunkId(null), 2000);
    } catch (err) {
      console.error("Failed to copy chunk:", err);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 font-sans cursor-pointer"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-3xl max-h-[85vh] shadow-2xl flex flex-col overflow-hidden cursor-default"
      >
        {/* Header */}
        <div className="p-4 border-b border-zinc-850 flex items-center justify-between bg-black">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center font-bold">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h3 id="source-modal-title" className="text-sm font-bold text-white">{file.file_name}</h3>
              <p className="text-[11px] text-zinc-400 uppercase font-mono">
                {file.modality} • {chunks.length} Extracted Semantic Chunks
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close source preview"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search Bar */}
        {chunks.length > 2 && (
          <div className="px-5 pt-3 pb-1">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-zinc-500" />
              <input
                type="text"
                placeholder="Search extracted chunk text..."
                value={chunkSearch}
                onChange={(e) => setChunkSearch(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600"
              />
            </div>
          </div>
        )}

        {/* Chunks List */}
        <div className="p-5 flex-1 overflow-y-auto space-y-3 text-xs">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2 text-zinc-500">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
              <span>Loading extracted document chunks...</span>
            </div>
          ) : filteredChunks.length === 0 ? (
            <p className="text-zinc-500 italic text-center py-12">
              {chunkSearch ? "No matching chunks found for search query." : "No extracted text chunks found."}
            </p>
          ) : (
            filteredChunks.map((chunk) => (
              <div
                key={chunk.id}
                className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 space-y-2"
              >
                <div className="flex items-center justify-between text-xs text-zinc-400 font-mono flex-wrap gap-2">
                  <span className="flex items-center gap-1 font-bold text-white">
                    <Bookmark className="w-3.5 h-3.5 text-zinc-400" />
                    Chunk #{chunk.chunk_index + 1}
                  </span>
                  <div className="flex items-center gap-2">
                    {chunk.page_number && (
                      <span className="bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800 text-zinc-300 text-[10px]">
                        Page {chunk.page_number}
                      </span>
                    )}
                    {chunk.cell_range && (
                      <span className="bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800 text-zinc-300 text-[10px]">
                        Cells: {chunk.cell_range}
                      </span>
                    )}
                    {chunk.audio_start_ms !== undefined && (
                      <span className="bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800 text-zinc-300 text-[10px]">
                        {chunk.audio_start_ms}ms – {chunk.audio_end_ms}ms
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => handleCopyChunk(chunk)}
                      className="text-xs text-zinc-400 hover:text-white inline-flex items-center gap-1 ml-1 cursor-pointer"
                    >
                      {copiedChunkId === chunk.id ? <Check className="w-3 h-3 text-white" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedChunkId === chunk.id ? "Copied" : "Copy"}</span>
                    </button>
                  </div>
                </div>
                <div className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed font-mono bg-zinc-950 p-2.5 rounded-lg border border-zinc-850">
                  {chunk.content}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
