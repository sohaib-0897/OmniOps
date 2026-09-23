"use client";
import { useRef, useState } from "react";
import { AlertCircle, Check, Clock3, FileUp, Loader2, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { formatBytes } from "@/lib/utils";

interface Props {
  workspaceId: string;
  onUploadComplete: () => void;
  compact?: boolean;
}
interface Upload {
  name: string;
  size: number;
  status: "queued" | "uploading" | "accepted" | "failed";
  error?: string;
}
const ALLOWED = [
  ".pdf",
  ".docx",
  ".xlsx",
  ".xls",
  ".csv",
  ".tsv",
  ".mp3",
  ".wav",
  ".m4a",
  ".ogg",
  ".png",
  ".jpg",
  ".jpeg",
  ".txt",
];
export function FileUploadZone({ workspaceId, onUploadComplete, compact = false }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [queue, setQueue] = useState<Upload[]>([]);
  const upload = async (selected: FileList | null) => {
    if (!selected?.length || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    const files = Array.from(selected);
    setQueue(
      files.map((file) => ({
        name: file.name,
        size: file.size,
        status: "queued",
      })),
    );
    const update = (index: number, change: Partial<Upload>) =>
      setQueue((items) =>
        items.map((item, current) =>
          current === index ? { ...item, ...change } : item,
        ),
      );
    for (const [index, file] of files.entries()) {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
      if (file.size > 50 * 1024 * 1024 || !ALLOWED.includes(extension)) {
        update(index, {
          status: "failed",
          error:
            file.size > 50 * 1024 * 1024
              ? "Choose a file smaller than 50 MB."
              : "This file format is not supported.",
        });
        continue;
      }
      update(index, { status: "uploading" });
      try {
        const form = new FormData();
        form.append("file", file);
        await apiClient.post(`/workspaces/${workspaceId}/files`, form);
        update(index, { status: "accepted" });
        onUploadComplete();
      } catch (err) {
        update(index, {
          status: "failed",
          error:
            err instanceof Error
              ? err.message
              : "Upload failed. Select the file again to retry.",
        });
      }
    }
    busyRef.current = false;
    setBusy(false);
    if (input.current) input.current.value = "";
  };
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="section-title">Upload sources</h2>
        <span className="text-[11px] text-zinc-400">50 MB / file</span>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
        accept={ALLOWED.join(",")}
        aria-label="Choose source files"
      />
      <button
        disabled={busy}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void upload(event.dataTransfer.files);
        }}
        className={`flex w-full items-center gap-3 rounded-md border border-dashed text-left transition-colors ${compact ? "px-3 py-2.5" : "p-4"} ${dragging ? "border-zinc-200 bg-zinc-800" : "border-zinc-700 hover:border-zinc-400"}`}
      >
        <FileUp className="h-5 w-5 shrink-0 text-zinc-300" />
        <span>
          <span className="block text-xs font-medium">
            {busy ? "Uploading sources" : "Drop files or browse"}
          </span>
          {!compact && <span className="mt-1 block text-[11px] leading-5 text-zinc-400">
            Documents, tables, images, and audio
          </span>}
        </span>
      </button>
      {queue.length > 0 && (
        <div className="rounded-md border border-zinc-800">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
            <span className="text-xs text-zinc-300">
              Upload queue · {queue.length}
            </span>
            {!busy && (
              <button
                className="btn-icon h-6 w-6"
                aria-label="Clear upload queue"
                onClick={() => setQueue([])}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div
            aria-live="polite"
            className="max-h-64 divide-y divide-zinc-800 overflow-y-auto"
          >
            {queue.map((item, index) => {
              const Icon =
                item.status === "uploading"
                  ? Loader2
                  : item.status === "accepted"
                    ? Check
                    : item.status === "failed"
                      ? AlertCircle
                      : Clock3;
              return (
                <div key={`${item.name}-${index}`} className="px-3 py-2.5">
                  <div className="flex items-start gap-2">
                    <Icon
                      className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${item.status === "uploading" ? "animate-spin" : ""} ${item.status === "failed" ? "text-red-300" : "text-zinc-400"}`}
                    />
                    <span className="min-w-0 flex-1 break-words text-xs text-zinc-200">
                      {item.name}
                    </span>
                  </div>
                  <p className="mt-1 pl-5 text-[11px] capitalize text-zinc-400">
                    {item.status} · {formatBytes(item.size, 1)}
                  </p>
                  {item.error && (
                    <p className="mt-1 break-words pl-5 text-xs leading-5 text-red-200">
                      {item.error}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      <details className="text-[11px] leading-5 text-zinc-400" open={compact ? undefined : true}>
        <summary className="text-zinc-400">Supported files and processing</summary>
        <p className="mt-2">Documents, tables, images, and audio. Up to 50 MB per file.</p>
        <p className="mt-1">
        Processing and extraction status appear in Sources. Upload acceptance
        does not mean extraction is complete.
        </p>
      </details>
    </section>
  );
}
