"use client";
import { useEffect, useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import { SourceDocument, DocumentChunk } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { formatDuration } from "@/lib/utils";
import { Dialog } from "@/components/ui/Dialog";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "@/components/ui/Primitives";

export function SourcePreviewModal({
  file,
  onClose,
}: {
  file: SourceDocument | null;
  onClose: () => void;
}) {
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setChunks([]);
    setQuery("");
    setCopied(null);
    setError(null);
    if (!file) return;
    setLoading(true);
    apiClient
      .get<DocumentChunk[]>(
        `/workspaces/${file.workspace_id}/files/${file.id}/preview`,
      )
      .then((data) => {
        if (alive) setChunks(data);
      })
      .catch((err) => {
        if (alive)
          setError(
            err instanceof Error
              ? err.message
              : "Extracted content could not be loaded.",
          );
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [file, retry]);
  const visible = useMemo(
    () =>
      chunks.filter((chunk) =>
        chunk.content.toLowerCase().includes(query.toLowerCase()),
      ),
    [chunks, query],
  );
  const copy = async (chunk: DocumentChunk) => {
    try {
      await navigator.clipboard.writeText(chunk.content);
      setCopied(chunk.id);
    } catch {
      setError(
        "Copy is unavailable. Select the excerpt text and copy it manually.",
      );
    }
  };
  return (
    <Dialog
      open={Boolean(file)}
      onClose={onClose}
      title={file?.file_name || "Source preview"}
      description="Extracted content and recorded source locations"
    >
      <div className="space-y-4">
        {file && (
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={file.processing_status} />
            <span className="meta-copy capitalize">
              {file.modality} · {chunks.length} {chunks.length === 1 ? "excerpt" : "excerpts"}
            </span>
          </div>
        )}
        {file?.error_message && (
          <ErrorState
            title="Extraction limitation"
            message={file.error_message}
          />
        )}
        {chunks.length > 2 && (
          <input
            aria-label="Search extracted content"
            className="field"
            placeholder="Search extracted content"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
        {loading ? (
          <LoadingState label="Loading extracted content" />
        ) : error ? (
          <ErrorState
            message={error}
            onRetry={() => setRetry((value) => value + 1)}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            title={
              query ? "No matching excerpts" : "No extracted content available"
            }
            description={
              query
                ? "Try another search term."
                : "Check the source processing status. Original-file rendering is not available in this preview."
            }
          />
        ) : (
          visible.map((chunk) => (
            <article
              key={chunk.id}
              className="border-b border-zinc-800 pb-5 last:border-0"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xs font-medium">
                  Excerpt {chunk.chunk_index + 1}
                </h3>
                <button className="btn-ghost" onClick={() => void copy(chunk)}>
                  {copied === chunk.id ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  {copied === chunk.id ? "Copied" : "Copy excerpt"}
                </button>
              </div>
              <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-400">
                {chunk.page_number != null && (
                  <span>Page {chunk.page_number}</span>
                )}
                {chunk.cell_range && <span>Cells {chunk.cell_range}</span>}
                {chunk.audio_start_ms != null && (
                  <span>
                    {formatDuration(chunk.audio_start_ms)} –{" "}
                    {formatDuration(chunk.audio_end_ms)}
                  </span>
                )}
                {typeof chunk.chunk_metadata?.speaker === "string" && (
                  <span>Speaker: {chunk.chunk_metadata.speaker}</span>
                )}
                {chunk.extraction_method && (
                  <span>{chunk.extraction_method.replace(/_/g, " ")}</span>
                )}
              </div>
              <blockquote className="whitespace-pre-wrap break-words border-l-2 border-zinc-600 pl-4 text-sm leading-7 text-zinc-300">
                {chunk.content}
              </blockquote>
              <details className="mt-4 text-xs text-zinc-400">
                <summary>Extraction details</summary>
                <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2">
                  <dt>Excerpt ID</dt>
                  <dd className="break-all font-mono">{chunk.id}</dd>
                  <dt>Lexical retrieval</dt>
                  <dd>{chunk.lexical_search_status || "Not reported"}</dd>
                  <dt>Semantic retrieval</dt>
                  <dd>{chunk.semantic_search_status || "Not reported"}</dd>
                  {chunk.embedding_model && (
                    <>
                      <dt>Embedding model</dt>
                      <dd className="break-words">{chunk.embedding_model}</dd>
                    </>
                  )}
                </dl>
              </details>
            </article>
          ))
        )}
      </div>
    </Dialog>
  );
}
