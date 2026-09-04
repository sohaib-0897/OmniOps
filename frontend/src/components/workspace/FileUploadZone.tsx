"use client";

import React, { useState, useRef } from "react";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

interface Props {
  workspaceId: string;
  onUploadComplete: () => void;
}

interface UploadingFile {
  name: string;
  size: number;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const ALLOWED_EXTS = [
  ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".tsv",
  ".mp3", ".wav", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".txt"
];

const MODALITY_PILLS = [
  "PDF", "XLSX", "CSV", "Audio", "DOCX", "Images", "TXT"
];

export function FileUploadZone({ workspaceId, onUploadComplete }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [fileQueue, setFileQueue] = useState<UploadingFile[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return `File exceeds 50MB limit (${(file.size / (1024 * 1024)).toFixed(1)}MB).`;
    }
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) {
      return `Unsupported file format '${ext}'.`;
    }
    return null;
  };

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setErrorMessage(null);

    const initialQueue: UploadingFile[] = Array.from(files).map((f) => ({
      name: f.name,
      size: f.size,
      status: "pending",
    }));
    setFileQueue(initialQueue);
    setIsUploading(true);

    let anySuccess = false;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const validationError = validateFile(file);

      if (validationError) {
        setFileQueue((prev) =>
          prev.map((item, idx) =>
            idx === i ? { ...item, status: "error", error: validationError } : item
          )
        );
        continue;
      }

      setFileQueue((prev) =>
        prev.map((item, idx) => (idx === i ? { ...item, status: "uploading" } : item))
      );

      try {
        const formData = new FormData();
        formData.append("file", file);

        await apiClient.post(`/workspaces/${workspaceId}/files`, formData);

        setFileQueue((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: "success" } : item))
        );
        anySuccess = true;
      } catch (err: any) {
        setFileQueue((prev) =>
          prev.map((item, idx) =>
            idx === i ? { ...item, status: "error", error: err.message || "Upload failed." } : item
          )
        );
      }
    }

    setIsUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (anySuccess) {
      onUploadComplete();
    }
  };

  return (
    <div className="space-y-3 font-sans">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`group border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all ${
          isDragging
            ? "border-zinc-500 bg-zinc-900"
            : "border-zinc-800 hover:border-zinc-700 bg-zinc-950 hover:bg-zinc-900/50"
        } ${isUploading ? "opacity-60 pointer-events-none" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
          accept=".pdf,.docx,.xlsx,.xls,.csv,.tsv,.mp3,.wav,.png,.jpg,.jpeg,.txt"
        />

        <div className="flex flex-col items-center justify-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center group-hover:text-white transition-colors">
            <UploadCloud className="w-4 h-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-white">
              {isUploading ? "Ingesting Lakehouse Data..." : "Upload Business Lakehouse Data"}
            </p>
            <p className="text-[11px] text-zinc-400 mt-0.5">
              Drag & drop Excel, CSV, PDF, Audio, or Images
            </p>
          </div>

          {/* Monochrome Modality Pills */}
          <div className="flex items-center gap-1.5 flex-wrap justify-center mt-1">
            {MODALITY_PILLS.map((label) => (
              <span
                key={label}
                className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-400"
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Per-File Upload Status Queue */}
      {fileQueue.length > 0 && (
        <div className="space-y-1.5 p-3 rounded-xl bg-zinc-950 border border-zinc-800">
          <div className="flex items-center justify-between text-xs font-bold text-zinc-300 pb-1 border-b border-zinc-850">
            <span>Upload Queue ({fileQueue.length})</span>
            {!isUploading && (
              <button
                type="button"
                onClick={() => setFileQueue([])}
                className="text-zinc-500 hover:text-zinc-300 transition-colors p-1"
                title="Clear queue"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
            {fileQueue.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-xs p-2 rounded-lg bg-zinc-900 border border-zinc-800"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {item.status === "uploading" && <Loader2 className="w-3.5 h-3.5 text-zinc-300 animate-spin shrink-0" />}
                  {item.status === "success" && <CheckCircle2 className="w-3.5 h-3.5 text-zinc-200 shrink-0" />}
                  {item.status === "error" && <AlertCircle className="w-3.5 h-3.5 text-zinc-400 shrink-0" />}
                  {item.status === "pending" && <FileText className="w-3.5 h-3.5 text-zinc-500 shrink-0" />}
                  <span className="truncate text-zinc-200 font-medium">{item.name}</span>
                </div>
                <span className="text-[10px] text-zinc-400 shrink-0 font-mono">
                  {(item.size / 1024).toFixed(0)} KB
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-2 text-xs text-zinc-200 bg-zinc-900 p-3 rounded-xl border border-zinc-800">
          <AlertCircle className="w-4 h-4 text-zinc-400 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
