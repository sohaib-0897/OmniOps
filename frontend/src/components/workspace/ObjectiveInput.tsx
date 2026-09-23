"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ArrowUp, FileText, Loader2, Paperclip, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { formatBytes } from "@/lib/utils";

interface Props {
  workspaceId: string;
  onStartInvestigation: (
    objective: string,
    maxSteps: number,
  ) => Promise<boolean | void> | boolean | void;
  onSourcesChanged: () => void;
  submitting?: boolean;
  variant?: "empty" | "another";
  sourceCount?: number;
  readySourceCount?: number;
  onInspectSources?: () => void;
}

interface Attachment {
  id: string;
  file: File;
  status: "ready" | "uploading" | "uploaded" | "failed";
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

const prompts = [
  "Analyze report",
  "Compare sources",
  "Find risks",
  "Summarize evidence",
];

export function ObjectiveInput({
  workspaceId,
  onStartInvestigation,
  onSourcesChanged,
  submitting = false,
  variant = "empty",
  sourceCount = 0,
  readySourceCount = 0,
  onInspectSources,
}: Props) {
  const [objective, setObjective] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const busy = working || submitting;

  useEffect(() => {
    const field = textarea.current;
    if (!field) return;
    const resize = () => {
      field.style.height = "auto";
      field.style.height = `${Math.min(field.scrollHeight, 280)}px`;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [objective]);

  const selectFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files || []);
    const incoming = selected.map((file, index): Attachment => {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
      const invalid =
        file.size > 50 * 1024 * 1024
          ? "Choose a file smaller than 50 MB."
          : !ALLOWED.includes(extension)
            ? "This file format is not supported."
            : undefined;
      return {
        id: `${file.name}:${file.size}:${file.lastModified}:${index}`,
        file,
        status: invalid ? "failed" : "ready",
        error: invalid,
      };
    });
    setAttachments((current) => [...current, ...incoming]);
    setError(null);
    event.target.value = "";
  };

  const updateAttachment = (id: string, change: Partial<Attachment>) =>
    setAttachments((items) =>
      items.map((item) => (item.id === id ? { ...item, ...change } : item)),
    );

  const run = async () => {
    if (!objective.trim() || busy) return;
    if (attachments.some((item) => item.status === "failed")) {
      setError("Remove files with errors before starting the investigation.");
      return;
    }
    setWorking(true);
    setError(null);
    try {
      for (const attachment of attachments.filter(
        (item) => item.status !== "uploaded",
      )) {
        updateAttachment(attachment.id, { status: "uploading", error: undefined });
        try {
          const form = new FormData();
          form.append("file", attachment.file);
          await apiClient.post(`/workspaces/${workspaceId}/files`, form);
          updateAttachment(attachment.id, { status: "uploaded" });
          onSourcesChanged();
        } catch (uploadError) {
          const message =
            uploadError instanceof Error
              ? uploadError.message
              : "The source could not be uploaded.";
          updateAttachment(attachment.id, {
            status: "failed",
            error: message,
          });
          throw new Error(message);
        }
      }
      const started = await onStartInvestigation(objective.trim(), 12);
      if (started !== false) {
        setObjective("");
        setAttachments([]);
      }
    } catch (runError) {
      setError(
        runError instanceof Error
          ? runError.message
          : "The investigation could not be started.",
      );
    } finally {
      setWorking(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run();
  };
  const shortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void run();
    }
  };

  return (
    <section
      className={`conversation-composer ${variant === "another" ? "conversation-composer-compact" : ""}`}
      aria-label={variant === "empty" ? "Start an investigation" : "Start another investigation"}
    >
      {variant === "empty" && (
        <div className="mb-9 text-center">
          <p className="type-label mb-5 text-zinc-400">OmniOps</p>
          <h1 className="type-display mx-auto max-w-xl">
            What do you want to investigate?
          </h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-zinc-400">
            Clear answers. Evidence you can inspect.
          </p>
        </div>
      )}
      {variant === "another" && (
        <div className="mb-3">
          <p className="text-xs leading-5 text-zinc-400">
            Starts a new investigation using this workspace&apos;s sources; prior answers are not used as conversation memory.
          </p>
        </div>
      )}

      <form onSubmit={submit}>
        <div className="composer-frame">
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 border-b border-zinc-800 px-3 py-3" aria-label="Attached files">
              {attachments.map((attachment) => (
                <span
                  key={attachment.id}
                  className={`attachment-chip ${attachment.status === "failed" ? "attachment-chip-error" : ""}`}
                  title={attachment.error || attachment.file.name}
                >
                  {attachment.status === "uploading" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FileText className="h-3.5 w-3.5" />
                  )}
                  <span className="max-w-48 truncate">{attachment.file.name}</span>
                  <span className="text-zinc-500">{formatBytes(attachment.file.size, 1)}</span>
                  {!busy && (
                    <button
                      type="button"
                      aria-label={`Remove ${attachment.file.name}`}
                      onClick={() =>
                        setAttachments((items) =>
                          items.filter((item) => item.id !== attachment.id),
                        )
                      }
                      className="rounded-sm text-zinc-500 hover:text-zinc-100"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          <label htmlFor={`objective-input-${variant}`} className="sr-only">
            Investigation question
          </label>
          <textarea
            ref={textarea}
            id={`objective-input-${variant}`}
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            onKeyDown={shortcut}
            disabled={busy}
            rows={2}
            placeholder={
              variant === "empty"
                ? "What would you like to understand?"
                : "Ask a new question about these sources…"
            }
            className="composer-textarea block w-full resize-none bg-transparent px-4 py-3 text-[15px] leading-6 text-zinc-100 outline-none placeholder:text-zinc-400 disabled:opacity-60"
          />
          <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              accept={ALLOWED.join(",")}
              onChange={selectFiles}
              aria-label="Attach source files"
            />
            <button
              type="button"
              className="btn-icon h-9 w-9"
              disabled={busy}
              aria-label="Attach source files"
              onClick={() => fileInput.current?.click()}
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <div className="min-w-0 flex-1 text-xs text-zinc-400" role="status">
              {sourceCount > 0 && onInspectSources && !busy ? <button type="button" className="rounded px-1 py-1 text-left hover:text-zinc-100" onClick={onInspectSources}>{readySourceCount === sourceCount ? `${sourceCount} ${sourceCount === 1 ? "source" : "sources"} ready` : `${readySourceCount} of ${sourceCount} sources ready`}</button> : <span>
              {busy ? "Starting investigation…" : sourceCount > 0
                ? `${readySourceCount} of ${sourceCount} ${sourceCount === 1 ? "source" : "sources"} ready`
                : "Attach files for context"}</span>}
            </div>
            <span className="hidden text-[11px] text-zinc-400 sm:inline">
              Shift + Enter ↵
            </span>
            <button
              type="submit"
              disabled={busy || !objective.trim()}
              className="composer-send flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-100 text-zinc-950 transition-colors enabled:hover:bg-zinc-300 disabled:bg-zinc-800 disabled:text-zinc-400"
              aria-label={busy ? "Starting investigation" : "Start investigation"}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
        {error && (
          <p role="alert" className="mt-2 text-xs leading-5 text-red-300">
            {error}
          </p>
        )}
      </form>

      {variant === "empty" && (
        <div className="mt-5 flex flex-wrap justify-center gap-2" aria-label="Example questions">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="rounded-md px-3 py-2 text-xs text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-100"
              disabled={busy}
              onClick={() => { setObjective(prompt); textarea.current?.focus(); }}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
